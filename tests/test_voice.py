import pytest

from isa9000.gemini import Gemini
from isa9000.voice import Speaker, SpeechError, record_episode

SCRIPT = "\n\n".join(
    " ".join(f"w{paragraph}x{word}" for word in range(60)) for paragraph in range(9)
)


@pytest.fixture
def speaker(gemini):
    return Speaker(Gemini(gemini), "speech-model", "Kore", "Warm.", "text-model")


@pytest.mark.parametrize("stretch", [1.0, 1.16, 1.28])
def test_natural_variation_is_kept(gemini, speaker, tmp_path, stretch):
    gemini.stretch = stretch
    record_episode(speaker, SCRIPT, tmp_path / "episode.mp3")
    assert (tmp_path / "episode.mp3").exists()
    assert gemini.calls.count("speech") == 1


@pytest.mark.parametrize("stretch", [0.8, 1.4, 30.0])
def test_lengths_outside_the_window_fail(gemini, speaker, tmp_path, stretch):
    gemini.stretch = stretch
    with pytest.raises(SpeechError):
        record_episode(speaker, SCRIPT, tmp_path / "episode.mp3")
    assert not (tmp_path / "episode.mp3").exists()


def test_unspoken_script_fails(gemini, speaker, tmp_path):
    gemini.heard = "something else entirely"
    with pytest.raises(SpeechError, match="opening words"):
        record_episode(speaker, SCRIPT, tmp_path / "episode.mp3")
