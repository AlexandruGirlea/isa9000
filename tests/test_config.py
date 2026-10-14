import tomllib

import pytest

from isa9000.config import Config, ConfigError, git_would_track, load_config, template
from isa9000.links import check_source


def test_template_matches_the_defaults():
    assert Config(**tomllib.loads(template())) == Config()


def test_config_from_the_environment(tmp_path, monkeypatch):
    settings = tmp_path / "custom.toml"
    settings.write_text('[narrator]\nvoice = "Aoede"\n')
    monkeypatch.setenv("ISA9000_CONFIG", str(settings))
    assert load_config().narrator.voice == "Aoede"


@pytest.mark.parametrize(
    ("setting", "problem"),
    [
        ('[narrator]\nvoise = "Aoede"', "narrator.voise"),
        ('[branding]\ngreeting = "Hi, {nmae}"', "{nmae}"),
    ],
)
def test_config_mistakes_are_named(tmp_path, setting, problem):
    settings = tmp_path / "isa9000.toml"
    settings.write_text(setting + "\n")
    with pytest.raises(ConfigError, match=problem):
        load_config(str(settings))


def test_models_and_voice_follow_the_provider():
    google = Config(provider="google")
    assert (google.models.text, google.narrator.voice) == ("gemini-3.1-pro-preview", "Kore")
    assert (Config().models.text, Config().narrator.voice) == ("gpt-6.1-sol", "en-US-Olivia")
    assert Config(models={"text": "gemini-3.1-pro-preview"}).provider == "google"


def test_git_would_not_track_outside_a_repository(tmp_path):
    assert not git_would_track(tmp_path / "isa9000.toml")


def test_local_sources_are_checked(tmp_path):
    (tmp_path / "policy.md").write_text("text")
    (tmp_path / "report.docx").write_text("text")
    (tmp_path / "empty").mkdir()
    assert check_source(str(tmp_path / "policy.md")).status == "file"
    assert check_source(str(tmp_path / "report.docx")).status == "unsupported"
    assert check_source(str(tmp_path / "missing.md")).status == "missing"
    assert check_source(str(tmp_path / "empty")).status == "empty"
    assert check_source(str(tmp_path)).status == "folder"
