from __future__ import annotations

import base64
import contextlib
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from isa9000.config import (
    DEFAULT_ICON,
    DEFAULT_MARKS,
    LOGO_TYPES,
    Config,
    ConfigError,
    credentials_problem,
    load_config,
)
from isa9000.links import check_source
from isa9000.podcast import MANIFEST, load_manifest, member

STATIC = pathlib.Path(__file__).resolve().parent / "static"
PRESENTATION_WEBSITE_ASSETS = (
    pathlib.Path(__file__).resolve().parent.parent / "presentation_website_static"
)
LOCAL_HOSTS = ("127.0.0.1", "localhost")
CREATE_STEPS = [
    ("check", "Checking your sources"),
    ("read", "Reading the material"),
    ("plan", "Planning the podcast"),
    ("write", "Writing and fact-checking episodes"),
    ("review", "Reviewing and polishing episodes"),
    ("record", "Recording the audio"),
    ("done", "Ready to listen"),
]
RECORD_STEPS = [("record", "Recording the audio"), ("done", "Ready to listen")]
STAGE_ALIASES = {"verify": "write"}
NEEDS_REVIEW = 3
PRESENTATION_WEBSITE_TIMEOUT_S = 900
STORED = {".mp3", ".jpg", ".jpeg", ".png", ".woff", ".woff2"}
# The audio generation UI tab shows the logo with a "record" badge, so it never looks like
# the presentation website tab.
FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<image href="data:{kind};base64,{data}" width="64" height="64"/>'
    '<circle cx="48" cy="48" r="15" fill="#ffffff"/>'
    '<circle cx="48" cy="48" r="9" fill="#e11d48"/>'
    "</svg>"
)


class SourceIn(BaseModel):
    source: str


class RecordIn(BaseModel):
    episodes: list[int] = []


class PodcastIn(BaseModel):
    request: str
    sources: list[str]
    text_only: bool = False
    follow_links: bool = False


def _command(config_path: str | None, *args: str) -> list[str]:
    command = [sys.executable, "-m", "isa9000", "--progress", "json"]
    if config_path:
        command += ["--config", config_path]
    return command + list(args)


class Job:
    # One command-line run at a time, followed through its JSON progress lines.

    def __init__(self, config_path: str | None) -> None:
        self.config_path = config_path
        self.lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self.state = "idle"
        self.steps: list[dict] = []
        self.log: list[str] = []
        self.error = ""
        self.folder: str | None = None
        self.started = 0.0
        self.finished = 0.0
        self.last: tuple[list[str], list[tuple[str, str]], set[str]] | None = None

    def start(
        self,
        args: list[str],
        steps: list[tuple[str, str]],
        skip: set[str] | None = None,
        keep_folder: bool = False,
    ) -> None:
        skip = skip or set()
        with self.lock:
            if self.state == "running":
                raise HTTPException(status_code=409, detail="a podcast is already being created")
            self.state, self.log, self.error = "running", [], ""
            self.steps = [
                {
                    "key": key,
                    "label": label,
                    "status": "skipped" if key in skip else "pending",
                    "detail": "",
                }
                for key, label in steps
            ]
            if not keep_folder:
                self.folder = None
            self.last = (list(args), steps, set(skip))
            self.started, self.finished = time.time(), 0.0
            self.process = subprocess.Popen(
                _command(self.config_path, *args),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        threading.Thread(target=self._follow, args=(self.process,), daemon=True).start()

    def _follow(self, process: subprocess.Popen) -> None:
        errors: list[str] = []
        reader = threading.Thread(target=lambda: errors.extend(process.stderr), daemon=True)
        reader.start()
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._apply(process, event)
        code = process.wait()
        reader.join(timeout=5)
        with self.lock:
            if process is not self.process or self.state != "running":
                return
            self.finished = time.time()
            last = next((line.strip() for line in reversed(errors) if line.strip()), "")
            if code == 0:
                self.state = "done"
                for step in self.steps:
                    if step["status"] != "skipped":
                        step["status"] = "done"
                return
            self.state = "review" if code == NEEDS_REVIEW else "failed"
            self.error = last.removeprefix("isa9000: ") or self.error or f"stopped (exit {code})"
            for step in self.steps:
                if step["status"] == "active":
                    step["status"] = "done" if code == NEEDS_REVIEW else "failed"

    def _apply(self, process: subprocess.Popen, event: dict) -> None:
        stage = STAGE_ALIASES.get(event.get("stage", ""), event.get("stage", ""))
        with self.lock:
            if process is not self.process or self.state != "running":
                return
            message = event.get("message", "")
            if message:
                self.log.append(message)
            if event.get("folder"):
                self.folder = event["folder"]
            if stage == "error":
                self.error = message
                return
            keys = [step["key"] for step in self.steps]
            if stage not in keys:
                return
            position = keys.index(stage)
            for index, step in enumerate(self.steps):
                if step["status"] == "skipped":
                    continue
                if index < position:
                    step["status"] = "done"
                elif index == position:
                    step["status"] = "done" if stage == "done" else "active"
                    current, total = event.get("current"), event.get("total")
                    if current and total:
                        step["detail"] = f"Episode {current} of {total}"
                    elif stage == "plan" and total:
                        step["detail"] = f"{total} episodes planned"

    def stop(self) -> None:
        with self.lock:
            if self.state != "running" or self.process is None:
                return
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            self.state, self.finished = "stopped", time.time()
            for step in self.steps:
                if step["status"] == "active":
                    step["status"] = "stopped"

    def reset(self) -> None:
        self.stop()
        if self.process is not None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        with self.lock:
            self.discard_partial()
            self.state, self.steps, self.log, self.error = "idle", [], [], ""
            self.folder, self.last, self.started, self.finished = None, None, 0.0, 0.0

    def discard_partial(self) -> None:
        # A run that never saved its podcast leaves only a partial folder behind.
        folder = pathlib.Path(self.folder) if self.folder else None
        if folder and folder.is_dir() and not (folder / MANIFEST).is_file():
            shutil.rmtree(folder)

    def podcast(self) -> dict | None:
        if not self.folder or not (pathlib.Path(self.folder) / MANIFEST).is_file():
            return None
        manifest = load_manifest(pathlib.Path(self.folder))
        return {
            "title": manifest["title"],
            "folder": self.folder,
            "notes": manifest.get("review", {}).get("notes", []),
            "episodes": [
                {
                    "number": entry["number"],
                    "title": entry["title"],
                    "audio": bool(entry.get("audio")),
                    "seconds": entry.get("seconds"),
                    "unverified": entry.get("unverified", []),
                    "audio_note": entry.get("audio_note", ""),
                }
                for entry in manifest["episodes"]
            ],
        }

    def episode_file(self, number: int, kind: str) -> pathlib.Path | None:
        if self.podcast() is None:
            return None
        folder = pathlib.Path(self.folder)
        for entry in load_manifest(folder)["episodes"]:
            name = entry.get("audio") if kind == "audio" else entry["transcript"]
            if entry["number"] == number and name:
                path = member(folder, name)
                return path if path.is_file() else None
        return None

    def snapshot(self) -> dict:
        with self.lock:
            end = self.finished or time.time()
            return {
                "state": self.state,
                "steps": [dict(step) for step in self.steps],
                "error": self.error,
                "log": list(self.log),
                "elapsed": int(end - self.started) if self.started else 0,
                "podcast": None if self.state == "running" and not self.folder else self.podcast(),
            }


def _zip(folder: pathlib.Path, name: str) -> FileResponse:
    handle, path = tempfile.mkstemp(suffix=".zip")
    os.close(handle)
    with zipfile.ZipFile(path, "w") as archive:
        for file in sorted(folder.rglob("*")):
            relative = file.relative_to(folder)
            if not file.is_file() or any(part.startswith(".") for part in relative.parts):
                continue
            kind = zipfile.ZIP_STORED if file.suffix.lower() in STORED else zipfile.ZIP_DEFLATED
            archive.write(file, f"{name}/{relative}", compress_type=kind)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{name}.zip",
        background=BackgroundTask(os.unlink, path),
    )


def create_app(config_path: str | None = None) -> FastAPI:
    job = Job(config_path)
    presentation_website_lock = threading.Lock()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        job.stop()

    app = FastAPI(
        title="isa9000 audio generation UI",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.job = job

    def config() -> Config:
        try:
            return load_config(config_path)
        except ConfigError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # The audio generation UI reads local files and spends API credit, so it only answers
        # on loopback: pin the Host header against DNS rebinding and refuse cross-site writes.
        host = request.headers.get("host", "")
        if host.split(":")[0] not in LOCAL_HOSTS:
            return JSONResponse({"detail": "bad host"}, status_code=421)
        origin = request.headers.get("origin")
        if request.method != "GET" and origin not in (None, f"http://{host}"):
            return JSONResponse({"detail": "cross-origin write"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        return response

    # Read once, so the page always matches the server code that is running.
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    styles = (STATIC / "theme.css").read_text(encoding="utf-8")

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse(page)

    @app.get("/theme.css")
    def theme() -> Response:
        return Response(styles, media_type="text/css")

    def image(path: pathlib.Path) -> FileResponse:
        kind = LOGO_TYPES.get(path.suffix.lower())
        if kind and path.is_file():
            return FileResponse(path, media_type=kind)
        raise HTTPException(status_code=404)

    @app.get("/favicon.svg")
    def favicon() -> Response:
        settings = config()
        path = settings.logo_file if settings.branding.logo else DEFAULT_ICON
        kind = LOGO_TYPES.get(path.suffix.lower())
        if not kind or not path.is_file():
            raise HTTPException(status_code=404)
        data = base64.b64encode(path.read_bytes()).decode()
        return Response(FAVICON.format(kind=kind, data=data), media_type="image/svg+xml")

    @app.get("/mark/{background}")
    def mark(background: str) -> FileResponse:
        settings = config()
        if settings.branding.logo or background not in DEFAULT_MARKS:
            return image(settings.logo_file)
        return image(DEFAULT_MARKS[background])

    @app.get("/api/config")
    def describe() -> dict:
        settings = config()
        return {
            "brand": settings.branding.brand,
            "powered_by": settings.branding.powered_by,
            "accent_color": settings.branding.accent_color,
            "narrator": settings.narrator.name,
            "output_folder": str(settings.output_folder.resolve()),
            "presentation_website_ready": (
                settings.presentation_website_folder / "index.html"
            ).is_file(),
            "config_file": str(settings.path) if settings.path else None,
            "problem": credentials_problem(settings),
        }

    @app.post("/api/check")
    def check(body: SourceIn) -> dict:
        return check_source(body.source).to_dict()

    @app.post("/api/podcasts")
    def start(body: PodcastIn) -> dict:
        config()
        if not body.request.strip() or not body.sources:
            raise HTTPException(status_code=400, detail="add a request and at least one source")
        args = ["create", f"--request={body.request}"]
        args += [f"--source={source}" for source in body.sources]
        if body.text_only:
            args.append("--text-only")
        if body.follow_links:
            args.append("--follow-links")
        job.start(args, CREATE_STEPS, skip={"record"} if body.text_only else set())
        return {"started": True}

    @app.post("/api/record")
    def record(body: RecordIn) -> dict:
        config()
        if job.podcast() is None:
            raise HTTPException(status_code=404, detail="no podcast to record")
        args = ["record", job.folder]
        for number in body.episodes:
            args += ["--episode", str(number)]
        job.start(args, RECORD_STEPS, keep_folder=True)
        return {"started": True}

    @app.post("/api/stop")
    def stop() -> dict:
        job.stop()
        return {"stopped": True}

    @app.post("/api/reset")
    def reset() -> dict:
        job.reset()
        return {"reset": True}

    @app.post("/api/retry")
    def retry() -> dict:
        config()
        if job.state not in ("failed", "stopped") or job.last is None:
            raise HTTPException(status_code=409, detail="nothing to retry")
        if job.podcast() is not None:
            job.start(["record", job.folder], RECORD_STEPS, keep_folder=True)
            return {"started": True}
        job.discard_partial()
        args, steps, skip = job.last
        job.start(args, steps, skip)
        return {"started": True}

    @app.get("/api/job")
    def status() -> dict:
        return job.snapshot()

    @app.get("/api/job/episodes/{number}/{kind}")
    def episode_file(number: int, kind: str) -> FileResponse:
        if kind not in ("audio", "transcript"):
            raise HTTPException(status_code=404)
        path = job.episode_file(number, kind)
        if path is None:
            raise HTTPException(status_code=404)
        media = "audio/mpeg" if kind == "audio" else "text/plain; charset=utf-8"
        return FileResponse(path, media_type=media)

    @app.get("/api/job/download")
    def download_podcast() -> FileResponse:
        if job.podcast() is None:
            raise HTTPException(status_code=404, detail="no podcast to download")
        folder = pathlib.Path(job.folder)
        return _zip(folder, folder.name)

    @app.post("/api/presentation-website")
    def build_presentation_website() -> dict:
        settings = config()
        if not presentation_website_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409, detail="the presentation website is already being built"
            )
        try:
            run = subprocess.run(
                _command(config_path, "presentation-website"),
                check=False,
                capture_output=True,
                text=True,
                timeout=PRESENTATION_WEBSITE_TIMEOUT_S,
            )
        finally:
            presentation_website_lock.release()
        if run.returncode != 0:
            message = run.stderr.strip().splitlines()[-1] if run.stderr.strip() else ""
            raise HTTPException(
                status_code=400,
                detail=message.removeprefix("isa9000: ")
                or "the presentation website could not be built",
            )
        library = json.loads(
            (settings.presentation_website_folder / "library.json").read_text(encoding="utf-8")
        )
        return {
            "folder": str(settings.presentation_website_folder.resolve()),
            "podcasts": len(library["podcasts"]),
            "episodes": sum(len(podcast["episodes"]) for podcast in library["podcasts"]),
        }

    @app.get("/api/presentation-website/download")
    def download_presentation_website() -> FileResponse:
        folder = config().presentation_website_folder
        if not (folder / "index.html").is_file():
            raise HTTPException(status_code=404, detail="build the presentation website first")
        return _zip(folder, folder.name)

    try:
        presentation_website_folder = load_config(config_path).presentation_website_folder
    except ConfigError:
        presentation_website_folder = Config().presentation_website_folder
    app.mount("/assets", StaticFiles(directory=PRESENTATION_WEBSITE_ASSETS), name="assets")
    app.mount(
        "/presentation-website",
        StaticFiles(directory=presentation_website_folder, html=True, check_dir=False),
        name="presentation-website",
    )
    return app
