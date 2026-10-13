from __future__ import annotations

import functools
import http.server
import io
import json
import re
import shutil
import struct
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader

from isa9000.config import (
    DEFAULT_COLOR,
    DEFAULT_MARKS,
    GIT_IGNORE_ALL,
    LOGO_TYPES,
    Config,
    load_config,
)
from isa9000.links import is_url
from isa9000.podcast import MANIFEST, load_manifest, member
from isa9000.progress import Progress, Step
from isa9000.version import __version__

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
MARKER = ".isa9000-presentation_website"
STATIC = Path(__file__).with_name("presentation_website_static")
RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


def slug(text: str, limit: int = 60) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return value[:limit].strip("-") or "item"


def _copy(source: Path, target: Path) -> None:
    if target.exists():
        same_size = target.stat().st_size == source.stat().st_size
        if same_size and target.stat().st_mtime >= source.stat().st_mtime:
            return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _unique(value: str, taken: set[str]) -> str:
    candidate, copy = value, 2
    while candidate in taken:
        candidate = f"{value}-{copy}"
        copy += 1
    taken.add(candidate)
    return candidate


def _source(ref: str) -> dict:
    # Local paths reveal folder structure, and query strings or user names in links can carry
    # access tokens, so only file names and the scheme, host and path of links are published.
    if not is_url(ref):
        return {"label": Path(ref).name or ref, "url": None}
    parts = urllib.parse.urlsplit(ref)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    url = urllib.parse.urlunsplit((parts.scheme, host, parts.path, "", ""))
    return {"label": f"{host.removeprefix('www.')}{parts.path}", "url": url}


def _created(manifest: dict) -> datetime:
    try:
        return datetime.fromisoformat(manifest["created"])
    except (KeyError, ValueError):
        return datetime.now(UTC)


def _summary(title: str, text: str) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if paragraphs and title in paragraphs[0]:
        paragraphs = paragraphs[1:]
    if not paragraphs:
        return ""
    return re.split(r"(?<=[.!?])\s+", paragraphs[0], maxsplit=1)[0]


def _collect(podcasts_root: Path, site_root: Path) -> list[dict]:
    podcasts = []
    taken: set[str] = set()
    for manifest_path in sorted(podcasts_root.glob(f"*/{MANIFEST}")):
        folder = manifest_path.parent
        manifest = load_manifest(folder)
        podcast_slug = _unique(slug(folder.name), taken)
        episodes = []
        for entry in manifest.get("episodes", []):
            audio = member(folder, entry["audio"]) if entry.get("audio") else None
            if audio is None or not audio.is_file():
                continue
            name = f"audio_kb/{podcast_slug}/{entry['number']:02d}-{slug(entry['title'])}"
            _copy(audio, site_root / f"{name}.mp3")
            transcript = member(folder, entry["transcript"])
            text = ""
            if transcript.is_file():
                _copy(transcript, site_root / f"{name}.txt")
                text = transcript.read_text(encoding="utf-8")
            episodes.append(
                {
                    "number": entry["number"],
                    "title": entry["title"],
                    "summary": entry.get("summary") or _summary(entry["title"], text),
                    "audio": f"{name}.mp3",
                    "transcript": f"{name}.txt" if transcript.is_file() else None,
                    "seconds": entry.get("seconds"),
                    "bytes": audio.stat().st_size,
                }
            )
        if episodes:
            podcasts.append(
                {
                    "slug": podcast_slug,
                    "cover": _cover(folder, manifest, site_root, podcast_slug),
                    "title": manifest["title"],
                    "description": manifest.get("description", ""),
                    "created": _created(manifest).isoformat(timespec="seconds"),
                    "tags": manifest.get("tags", []),
                    "fact_checked": manifest.get("review", {}).get("fact_checked", True),
                    "sources": [_source(ref) for ref in manifest.get("sources", [])],
                    "episodes": episodes,
                }
            )
    podcasts.sort(key=lambda podcast: podcast["created"], reverse=True)
    return podcasts


def _url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + urllib.parse.quote(path)


def _feed(
    config: Config,
    title: str,
    description: str,
    link: str,
    podcasts: list[dict],
    image: str | None,
    serial: bool,
) -> bytes:
    ET.register_namespace("itunes", ITUNES)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, "generator").text = f"isa9000 {__version__}"
    ET.SubElement(channel, f"{{{ITUNES}}}author").text = config.branding.brand
    ET.SubElement(channel, f"{{{ITUNES}}}type").text = "serial" if serial else "episodic"
    if image:
        ET.SubElement(channel, f"{{{ITUNES}}}image", {"href": image})
    base_url = config.presentation_website.base_url
    for podcast in podcasts:
        created = datetime.fromisoformat(podcast["created"])
        for episode in podcast["episodes"]:
            item = ET.SubElement(channel, "item")
            label = episode["title"] if serial else f"{podcast['title']}: {episode['title']}"
            ET.SubElement(item, "title").text = label
            ET.SubElement(item, "description").text = episode["summary"] or podcast["description"]
            ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = episode["audio"]
            published = created + timedelta(minutes=episode["number"])
            ET.SubElement(item, "pubDate").text = format_datetime(published)
            ET.SubElement(
                item,
                "enclosure",
                {
                    "url": _url(base_url, episode["audio"]),
                    "length": str(episode["bytes"]),
                    "type": "audio/mpeg",
                },
            )
            if episode["seconds"]:
                ET.SubElement(item, f"{{{ITUNES}}}duration").text = str(int(episode["seconds"]))
            ET.SubElement(item, f"{{{ITUNES}}}episode").text = str(episode["number"])
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def _cover(folder: Path, manifest: dict, site_root: Path, podcast_slug: str) -> str | None:
    source = member(folder, manifest["cover"]) if manifest.get("cover") else None
    if source is None or not source.is_file():
        return None
    name = f"audio_kb/{podcast_slug}/cover{source.suffix.lower()}"
    _copy(source, site_root / name)
    return name


def _logo(config: Config, site_root: Path) -> str | None:
    source = config.logo_file
    if not source.is_file() or source.suffix.lower() not in LOGO_TYPES:
        return None
    name = f"logo{source.suffix.lower()}"
    _copy(source, site_root / name)
    return name


def _marks(config: Config, logo: str | None, site_root: Path) -> dict:
    # The default logo also comes as a transparent eye, one for dark and one for light navbars.
    if config.branding.logo or not logo:
        return {"on_dark": logo, "on_light": logo}
    marks = {}
    for background, source in DEFAULT_MARKS.items():
        _copy(source, site_root / source.name)
        marks[background] = source.name
    return marks


def _icon_sizes(path: Path) -> str:
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return "any"
    width, height = struct.unpack(">II", header[16:24])
    return f"{width}x{height}"


def _web_app(site: dict, site_root: Path) -> None:
    # Lets colleagues add the library to their phone's home screen like an app.
    manifest = {
        "name": site["title"],
        "short_name": site["title"][:12],
        "description": site["description"],
        "start_url": "index.html",
        "scope": "./",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": site["color"],
    }
    if site["logo"]:
        logo = site_root / site["logo"]
        manifest["icons"] = [
            {
                "src": site["logo"],
                "sizes": _icon_sizes(logo),
                "type": site["logo_type"],
                "purpose": "any",
            }
        ]
    (site_root / "manifest.webmanifest").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _prune(site_root: Path, keep: set[str]) -> None:
    podcasts_dir = site_root / "audio_kb"
    if not podcasts_dir.is_dir():
        return
    for child in podcasts_dir.iterdir():
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child)
        elif child.suffix == ".html" and child.stem not in keep:
            child.unlink()


def _prepare(site_root: Path) -> None:
    if site_root.exists() and any(site_root.iterdir()) and not (site_root / MARKER).exists():
        raise ValueError(
            f"{site_root} is not empty and was not created by isa9000; choose another folder"
        )
    site_root.mkdir(parents=True, exist_ok=True)
    (site_root / MARKER).write_text("Built by isa9000. Safe to delete and rebuild.\n")
    (site_root / ".gitignore").write_text(GIT_IGNORE_ALL)


def _duration(seconds: float | None) -> str:
    if not seconds:
        return ""
    minutes, rest = divmod(int(seconds), 60)
    if minutes >= 60:
        return f"{minutes // 60}h {minutes % 60}m"
    return f"{minutes}m {rest:02d}s"


def _total_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}h {minutes % 60}m"


def _page(podcast: dict, site_root: Path) -> dict:
    created = datetime.fromisoformat(podcast["created"])
    seconds = int(sum(episode["seconds"] or 0 for episode in podcast["episodes"]))
    episodes = [
        {
            **episode,
            "audio_url": episode["audio"].removeprefix("audio_kb/"),
            "duration_label": _duration(episode["seconds"]),
            "text": (site_root / episode["transcript"]).read_text(encoding="utf-8")
            if episode["transcript"]
            else "",
        }
        for episode in podcast["episodes"]
    ]
    return {
        **podcast,
        "episodes": episodes,
        "episode_count": len(episodes),
        "total_duration": _total_duration(seconds) if seconds else "",
        "date_label": f"{created.day} {created:%B %Y}",
        "feed_href": podcast["feed"].removeprefix("audio_kb/") if podcast.get("feed") else "",
        "cover_url": podcast["cover"].removeprefix("audio_kb/") if podcast["cover"] else "",
    }


def build_presentation_website(
    config: Config | None = None,
    podcasts: str | Path | None = None,
    output: str | Path | None = None,
    progress: Progress = print,
) -> Path:
    config = config or load_config()
    podcasts_root = Path(podcasts).expanduser() if podcasts else config.output_folder
    site_root = Path(output).expanduser() if output else config.presentation_website_folder
    if not podcasts_root.is_dir():
        raise ValueError(f"audio knowledge base folder not found: {podcasts_root}")
    _prepare(site_root)

    progress(Step("presentation_website", f"Collecting podcasts from {podcasts_root}"))
    library = _collect(podcasts_root, site_root)
    _prune(site_root, {podcast["slug"] for podcast in library})
    logo = _logo(config, site_root)
    title = config.presentation_website.title or config.branding.brand
    base_url = config.presentation_website.base_url

    feed = None
    if base_url:
        image = _url(base_url, logo) if logo else None
        for podcast in library:
            podcast["feed"] = f"audio_kb/{podcast['slug']}/feed.xml"
            body = _feed(
                config,
                f"{title}: {podcast['title']}",
                podcast["description"],
                _url(base_url, f"audio_kb/{podcast['slug']}.html"),
                [podcast],
                _url(base_url, podcast["cover"]) if podcast["cover"] else image,
                serial=True,
            )
            (site_root / podcast["feed"]).write_bytes(body)
        feed = "feed.xml"
        everything = _feed(
            config,
            title,
            config.presentation_website.description,
            base_url,
            library,
            image,
            serial=False,
        )
        (site_root / feed).write_bytes(everything)
    else:
        progress(
            Step(
                "presentation_website",
                "No [presentation_website] base_url set: building without podcast feeds",
            )
        )

    color = config.branding.accent_color or DEFAULT_COLOR
    site = {
        "title": title,
        "heading": config.presentation_website.heading,
        "description": config.presentation_website.description,
        "brand": config.branding.brand,
        "powered_by": config.branding.powered_by,
        "color": color,
        "custom_color": color if color.lower() != DEFAULT_COLOR.lower() else "",
        "logo": logo,
        "marks": _marks(config, logo, site_root),
        "logo_type": LOGO_TYPES[Path(logo).suffix] if logo else "",
        "feed": feed,
    }
    _web_app(site, site_root)
    data = {
        **site,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "podcasts": library,
    }
    (site_root / "library.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    shutil.copytree(STATIC, site_root, dirs_exist_ok=True)
    templates = Environment(
        loader=PackageLoader("isa9000", "presentation_website_templates"), autoescape=True
    )
    pages = [_page(podcast, site_root) for podcast in library]
    home = templates.get_template("index.html").render(
        site=site,
        podcasts=pages,
        tags=sorted({tag for page in pages for tag in page["tags"]}),
        total_podcasts=len(pages),
        total_episodes=sum(page["episode_count"] for page in pages),
        fact_check=all(podcast["fact_checked"] for podcast in library),
        base_path="",
    )
    (site_root / "index.html").write_text(home, encoding="utf-8")
    podcast_page = templates.get_template("podcast.html")
    for page in pages:
        body = podcast_page.render(site=site, podcast=page, base_path="../", nav_path="../")
        (site_root / "audio_kb" / f"{page['slug']}.html").write_text(body, encoding="utf-8")

    episodes = sum(len(podcast["episodes"]) for podcast in library)
    progress(
        Step(
            "done",
            f"Presentation website ready in {site_root}: "
            f"{len(library)} podcasts, {episodes} episodes",
            folder=str(site_root),
        )
    )
    return site_root


class _Preview(http.server.SimpleHTTPRequestHandler):
    # Browsers can only seek in audio when the server answers byte-range requests.
    def send_head(self):
        match = RANGE.match(self.headers.get("Range", ""))
        path = Path(self.translate_path(self.path))
        if not match or not any(match.groups()) or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        first, last = match.groups()
        start = int(first) if first else max(size - int(last), 0)
        end = min(int(last), size - 1) if first and last else size - 1
        if start > end:
            self.send_error(416)
            return None
        with path.open("rb") as handle:
            handle.seek(start)
            body = handle.read(end - start + 1)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return io.BytesIO(body)


def serve_presentation_website(folder: Path, port: int) -> None:
    handler = functools.partial(_Preview, directory=str(folder))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Previewing on http://127.0.0.1:{port}  (ctrl-c to stop)")
        server.serve_forever()
