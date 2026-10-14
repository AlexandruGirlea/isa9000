from __future__ import annotations

import io
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from isa9000.links import HEADERS, TIMEOUT, is_url, supported_files
from isa9000.progress import Progress, Step

MAX_SOURCE_CHARS = 150_000
MAX_TOTAL_CHARS = 600_000
MAX_LINKED_PAGES = 25
MAX_INLINE_PDF_BYTES = 18_000_000
MIN_PAGE_CHARS = 500
NOISE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]
PDF_PROMPT = """Extract ALL content from this PDF. You MUST include:
- Title, owner or authors, date, and summary
- Every section with full text
- DESCRIBE every figure, diagram and chart in detail (what it shows, labels, relationships \
between parts)
- REPRODUCE every table as structured text with all rows and columns
- Describe formulas in plain words
- Key numbers and findings
- Conclusions and references

Output as structured plain text with clear section headers. Preserve all terminology and \
specific values."""


@dataclass
class Source:
    ref: str
    title: str
    text: str


def _clean(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return text.strip()


def _from_html(html: str, fallback: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    return title or fallback, _clean(root.get_text("\n"))


def _from_pdf(data: bytes, client, model: str) -> str:
    # The model reads tables and figures that plain text extraction loses.
    if client is not None and len(data) <= MAX_INLINE_PDF_BYTES:
        text = _clean(client.read_pdf(model, data, PDF_PROMPT))
        if text:
            return text
    reader = PdfReader(io.BytesIO(data))
    return _clean("\n\n".join(page.extract_text() or "" for page in reader.pages))


def _linked_pages(url: str, html: str) -> list[str]:
    # Links under the page's folder: its siblings and sub-pages.
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    prefix = path.rstrip("/") if path.endswith("/") else path.rsplit("/", 1)[0]
    found: list[str] = []
    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = anchor["href"]
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        if len(anchor.get_text(" ", strip=True)) < 2:
            continue
        link = urllib.parse.urlparse(urllib.parse.urljoin(url, href))._replace(fragment="")
        in_scope = not prefix or link.path == prefix or link.path.startswith(prefix + "/")
        clean = urllib.parse.urlunparse(link)
        if link.netloc == parsed.netloc and in_scope and clean != url and clean not in found:
            found.append(clean)
    return found


def _load_url(url: str, client, model: str) -> tuple[Source, list[str]]:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    kind = response.headers.get("content-type", "").lower()
    name = url.rstrip("/").rsplit("/", 1)[-1] or url
    if "pdf" in kind or url.lower().endswith(".pdf"):
        return Source(url, name, _from_pdf(response.content, client, model)), []
    if "html" in kind or "<html" in response.text[:2000].lower():
        title, text = _from_html(response.text, name)
        return Source(url, title, text), _linked_pages(response.url, response.text)
    return Source(url, name, _clean(response.text)), []


def _load_file(path: Path, client, model: str) -> Source:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return Source(str(path), path.stem, _from_pdf(path.read_bytes(), client, model))
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in (".html", ".htm"):
        title, text = _from_html(raw, path.stem)
        return Source(str(path), title, text)
    return Source(str(path), path.stem, _clean(raw))


def _load_linked(
    links: list[str], known: set[str], client, model: str, progress: Progress
) -> list[Source]:
    pending = [link for link in dict.fromkeys(links) if link not in known][:MAX_LINKED_PAGES]
    if pending:
        progress(Step("read", f"Reading {len(pending)} linked page(s)"))
    loaded = []
    for link in pending:
        try:
            source, _ = _load_url(link, client, model)
        except requests.RequestException as error:
            progress(
                Step("read", f"Skipped a linked page that could not be read: {link} ({error})")
            )
            continue
        loaded.append(source)
    return loaded


def _within_budget(documents: list[Source], progress: Progress) -> list[Source]:
    kept: list[Source] = []
    budget = MAX_TOTAL_CHARS
    for source in documents:
        text = source.text[: min(MAX_SOURCE_CHARS, budget)]
        if len(text) < len(source.text):
            progress(Step("read", f"Using the first {len(text):,} characters of {source.title}"))
        if text:
            kept.append(Source(source.ref, source.title, text))
            budget -= len(text)
        if budget <= 0:
            break
    return kept


def thin_pages(sources: list[Source]) -> list[Source]:
    return [
        source for source in sources if is_url(source.ref) and len(source.text) < MIN_PAGE_CHARS
    ]


def load_sources(
    refs: list[str],
    client=None,
    model: str = "",
    progress: Progress = print,
    follow_links: bool = False,
) -> list[Source]:
    documents: list[Source] = []
    links: list[str] = []
    for ref in refs:
        if is_url(ref):
            source, found = _load_url(ref, client, model)
            documents.append(source)
            links += found
            continue
        path = Path(ref).expanduser()
        files = supported_files(path) if path.is_dir() else [path]
        documents += [_load_file(file, client, model) for file in files]
    if follow_links:
        documents += _load_linked(links, set(refs), client, model, progress)
    return _within_budget(documents, progress)
