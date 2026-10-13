import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from isa9000.audio_generation_ui.app import create_app


@pytest.fixture
def audio_generation_ui(tmp_path):
    settings = tmp_path / "isa9000.toml"
    settings.write_text(
        f'[output]\nfolder = "{tmp_path / "audio_kb"}"\n'
        f'[presentation_website]\nfolder = "{tmp_path / "site"}"\n'
    )
    app = create_app(str(settings))
    return app, TestClient(app, base_url="http://127.0.0.1")


def test_only_local_requests_are_served(audio_generation_ui):
    _, client = audio_generation_ui
    assert client.get("/").status_code == 200
    assert client.get("/", headers={"host": "intranet.example.com"}).status_code == 421
    assert client.post("/api/reset", headers={"origin": "https://example.com"}).status_code == 403


def test_download_leaves_out_hidden_files(audio_generation_ui, tmp_path):
    app, client = audio_generation_ui
    folder = tmp_path / "audio_kb" / "2026-10-13 - Policy"
    folder.mkdir(parents=True)
    (folder / "podcast.json").write_text(json.dumps({"title": "Policy", "episodes": []}))
    (folder / "01 - Intro.txt").write_text("Hi.")
    (folder / ".notes").write_text("private")
    app.state.job.folder = str(folder)
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/job/download").content))
    assert sorted(archive.namelist()) == [
        "2026-10-13 - Policy/01 - Intro.txt",
        "2026-10-13 - Policy/podcast.json",
    ]
