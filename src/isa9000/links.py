from __future__ import annotations

import re
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; isa9000)"}
TIMEOUT = 20
MAX_SOURCES = 10
MAX_URL_CHARS = 2000
SUPPORTED_FILES = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf"}
SIGN_IN_HOSTS = {"login.microsoftonline.com", "accounts.google.com", "login.live.com"}
SIGN_IN_PATHS = ("/login", "/signin", "/sign-in", "/oauth", "/saml", "/sso")
NOT_FOUND_TITLE = re.compile(r"\b404\b|not found", re.IGNORECASE)


@dataclass
class SourceStatus:
    source: str
    ok: bool
    status: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _sign_in_page(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return (
        host in SIGN_IN_HOSTS
        or host.startswith(("login.", "auth.", "sso."))
        or any(marker in path for marker in SIGN_IN_PATHS)
    )


def _error_page(response: requests.Response) -> bool:
    # Some sites answer a missing page with 200; judge only the page given.
    return bool(NOT_FOUND_TITLE.search(_title(response.text)))


def _check_url(source: str) -> SourceStatus:
    if len(source) > MAX_URL_CHARS:
        detail = f"{len(source):,} characters; a link can have at most {MAX_URL_CHARS:,}"
        return SourceStatus(source, False, "too_long", detail)
    try:
        response = requests.get(source, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as error:
        return SourceStatus(source, False, "unreachable", type(error).__name__)
    code = response.status_code
    if code in (401, 403, 407) or _sign_in_page(response.url):
        return SourceStatus(source, False, "access_refused", "needs sign-in or a connector")
    if code in (404, 410):
        return SourceStatus(source, False, "not_found", f"HTTP {code}")
    if code != 200:
        return SourceStatus(source, False, "unreachable", f"HTTP {code}")
    if "html" in response.headers.get("content-type", "").lower() and _error_page(response):
        return SourceStatus(source, False, "error_page", "the page says it was not found")
    return SourceStatus(source, True, "reachable", f"HTTP {code}")


def supported_files(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_FILES
    )


def _check_path(source: str) -> SourceStatus:
    path = Path(source).expanduser()
    if not path.exists():
        return SourceStatus(source, False, "missing", "no such file or folder")
    if path.is_dir():
        count = len(supported_files(path))
        if not count:
            return SourceStatus(source, False, "empty", "no txt, md, html or pdf files")
        return SourceStatus(source, True, "folder", f"{count} supported files")
    if path.suffix.lower() not in SUPPORTED_FILES:
        kind = path.suffix or "files without an extension"
        return SourceStatus(source, False, "unsupported", f"{kind} is not supported")
    return SourceStatus(source, True, "file", f"{path.stat().st_size:,} bytes")


def check_source(source: str) -> SourceStatus:
    source = source.strip()
    if not source:
        return SourceStatus(source, False, "empty", "nothing to check")
    return _check_url(source) if is_url(source) else _check_path(source)


def check_sources(sources: list[str]) -> list[SourceStatus]:
    statuses, documents = [], 0
    for status in map(check_source, sources):
        folder = status.status == "folder"
        documents += len(supported_files(Path(status.source).expanduser())) if folder else 1
        if status.ok and documents > MAX_SOURCES:
            status.ok, status.status = False, "too_many"
            status.detail = (
                f"brings the total to {documents} documents; "
                f"a podcast can use at most {MAX_SOURCES}"
            )
        statuses.append(status)
    return statuses
