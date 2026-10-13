import functools
import http.server
import json
import shutil
import threading
import urllib.request

import pytest

from isa9000.config import Config
from isa9000.presentation_website import _Preview, _source, build_presentation_website
from isa9000.voice import to_mp3


def quiet(step):
    pass


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / "audio_kb" / "2026-10-13 - Expense Policy"
    folder.mkdir(parents=True)
    to_mp3(b"\x00\x00" * 48_000, 24_000, folder / "01 - What Changed.mp3")
    (folder / "01 - What Changed.txt").write_text("Hi.\n\nClaims are due within 60 days.\n\nBye.\n")
    manifest = {
        "title": "Expense Policy",
        "description": "What changed.",
        "created": "2026-10-13T08:00:00+00:00",
        "sources": ["/private/policies/expenses.pdf"],
        "tags": ["Finance"],
        "episodes": [
            {
                "number": 1,
                "title": "What Changed",
                "summary": "The new deadline.",
                "transcript": "01 - What Changed.txt",
                "audio": "01 - What Changed.mp3",
                "seconds": 2.0,
            }
        ],
    }
    (folder / "podcast.json").write_text(json.dumps(manifest))
    return folder.parent


def test_presentation_website_lists_podcasts_without_local_paths(library, tmp_path):
    config = Config(presentation_website={"base_url": "https://audio.example.com/"})
    site = build_presentation_website(
        config, podcasts=library, output=tmp_path / "site", progress=quiet
    )
    page = (site / "audio_kb" / "2026-10-13-expense-policy.html").read_text()
    assert 'data-tag="Finance"' in (site / "index.html").read_text()
    assert "expenses.pdf" in page and "/private/policies" not in page
    assert (site / "feed.xml").read_text().count("<item>") == 1
    assert (site / ".gitignore").is_file()


def test_source_links_drop_credentials_and_queries():
    assert _source("https://user:secret@wiki.example.com/travel?token=abc#top") == {
        "label": "wiki.example.com/travel",
        "url": "https://wiki.example.com/travel",
    }


def test_similar_podcast_names_get_their_own_pages(library, tmp_path):
    shutil.copytree(
        library / "2026-10-13 - Expense Policy", library / "2026-10-13 - Expense Policy!"
    )
    site = build_presentation_website(
        Config(), podcasts=library, output=tmp_path / "site", progress=quiet
    )
    assert sorted(page.name for page in (site / "audio_kb").glob("*.html")) == [
        "2026-10-13-expense-policy-2.html",
        "2026-10-13-expense-policy.html",
    ]


def test_removed_podcasts_leave_the_presentation_website(library, tmp_path):
    site = build_presentation_website(
        Config(), podcasts=library, output=tmp_path / "site", progress=quiet
    )
    shutil.rmtree(library / "2026-10-13 - Expense Policy")
    build_presentation_website(Config(), podcasts=library, output=site, progress=quiet)
    assert not list((site / "audio_kb").iterdir())


def test_unrelated_folder_is_refused(library, tmp_path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "notes.txt").write_text("mine")
    with pytest.raises(ValueError, match="not created by isa9000"):
        build_presentation_website(
            Config(), podcasts=library, output=tmp_path / "site", progress=quiet
        )


def test_preview_answers_byte_ranges(tmp_path):
    data = bytes(range(256)) * 40
    (tmp_path / "episode.mp3").write_bytes(data)
    handler = functools.partial(_Preview, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/episode.mp3"
    request = urllib.request.Request(url, headers={"Range": "bytes=100-199"})
    with urllib.request.urlopen(request) as response:
        assert response.status == 206
        assert response.headers["Content-Range"] == f"bytes 100-199/{len(data)}"
        assert response.read() == data[100:200]
    server.shutdown()
