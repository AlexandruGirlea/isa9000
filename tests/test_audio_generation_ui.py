import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from isa9000.audio_generation_ui.app import create_app
from isa9000.config import load_config


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


def test_settings_are_saved_in_the_config_file(audio_generation_ui, tmp_path):
    _, client = audio_generation_ui
    settings = tmp_path / "isa9000.toml"
    settings.write_text('# Ours\n[narrator]\nname = "Isabela"  # host\n' + settings.read_text())
    choices = client.get("/api/settings").json()
    choices.update(name="Ana", pronunciations={"Nginx": "engine x"}, quality="thorough")
    assert client.post("/api/settings", json=choices).status_code == 200
    saved = load_config(str(settings))
    assert settings.read_text().startswith('# Ours\n[narrator]\nname = "Ana"  # host\n')
    assert (saved.narrator.name, saved.narrator.voice, saved.output.quality) == (
        "Ana",
        "en-US-Serena",
        "thorough",
    )
    assert saved.narrator.pronunciations == {"Nginx": "engine x"}


def test_edited_transcript_is_saved(audio_generation_ui, tmp_path):
    app, client = audio_generation_ui
    folder = tmp_path / "audio_kb" / "2026-10-14 - Policy"
    folder.mkdir(parents=True)
    episode = {"number": 1, "title": "Intro", "transcript": "01 - Intro.txt"}
    (folder / "podcast.json").write_text(json.dumps({"title": "Policy", "episodes": [episode]}))
    (folder / "01 - Intro.txt").write_text("Hi.\n")
    app.state.job.folder = str(folder)
    assert (
        client.post("/api/job/episodes/1/transcript", json={"text": "Hello. "}).status_code == 200
    )
    assert (folder / "01 - Intro.txt").read_text() == "Hello.\n"
