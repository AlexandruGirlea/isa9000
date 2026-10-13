import json

import pytest

from isa9000.cli import main
from isa9000.config import Config
from isa9000.podcast import MANIFEST, create_podcast, member, record_podcast


def quiet(step):
    pass


@pytest.fixture
def config(tmp_path):
    return Config(output={"folder": str(tmp_path / "audio_kb")})


def test_approved_podcast_is_recorded(gemini, source, config):
    result = create_podcast("What changed?", [str(source)], config=config, progress=quiet)
    assert result.approved
    assert [episode.audio.name for episode in result.episodes] == [
        "01 - Episode 1.mp3",
        "02 - Episode 2.mp3",
    ]
    assert json.loads((result.folder / MANIFEST).read_text())["cover"] == "cover.png"
    assert (result.folder.parent / ".gitignore").read_text().endswith("*\n")


def test_fact_check_problems_are_fixed(gemini, source, config):
    gemini.problems = [["claims 30 days; the sources say 60"], [], []]
    result = create_podcast(
        "What changed?", [str(source)], config=config, audio=False, progress=quiet
    )
    assert gemini.calls.count("write") == 3
    assert not any(episode.unverified for episode in result.episodes)


def test_weak_episodes_are_polished(gemini, source, config):
    gemini.scores = [7, 9]
    result = create_podcast(
        "What changed?", [str(source)], config=config, audio=False, progress=quiet
    )
    assert result.approved
    assert gemini.calls.count("score") == 2


def test_podcast_below_the_bar_is_not_recorded(gemini, source, config):
    gemini.scores = [6]
    result = create_podcast("What changed?", [str(source)], config=config, progress=quiet)
    assert not result.approved and result.notes
    assert "speech" not in gemini.calls


@pytest.mark.parametrize("text_only", [[], ["--text-only"]])
def test_create_exits_3_when_review_is_needed(gemini, source, tmp_path, capsys, text_only):
    gemini.scores = [6]
    settings = tmp_path / "isa9000.toml"
    settings.write_text(f'[output]\nfolder = "{tmp_path / "audio_kb"}"\n')
    args = ["--config", str(settings), "create", "-r", "What changed?", "-s", str(source)]
    assert main(args + text_only) == 3
    assert "needs review" in capsys.readouterr().err


def test_one_episode_is_recorded_again(gemini, source, config):
    result = create_podcast("What changed?", [str(source)], config=config, progress=quiet)
    gemini.calls.clear()
    record_podcast(result.folder, config, progress=quiet, episodes={2})
    assert gemini.calls.count("speech") == 1


def test_refused_script_is_rephrased(gemini, source, config):
    result = create_podcast(
        "What changed?", [str(source)], config=config, audio=False, progress=quiet
    )
    gemini.refusals = 1
    recorded = record_podcast(result.folder, config, progress=quiet, episodes={1})
    assert recorded.episodes[0].audio is not None
    assert recorded.episodes[0].audio_note.startswith("the voice refused")


@pytest.mark.parametrize("name", ["../notes.txt", "/etc/hosts", ".hidden", ""])
def test_manifest_names_only_files_in_its_folder(tmp_path, name):
    with pytest.raises(ValueError, match="outside its folder"):
        member(tmp_path, name)


def test_unknown_episode_is_an_error(gemini, source, config):
    result = create_podcast(
        "What changed?", [str(source)], config=config, audio=False, progress=quiet
    )
    with pytest.raises(ValueError, match="no episode 9"):
        record_podcast(result.folder, config, progress=quiet, episodes={9})
