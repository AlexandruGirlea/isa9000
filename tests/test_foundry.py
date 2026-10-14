import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest
import requests

from isa9000.foundry import Foundry
from isa9000.voice import Speaker, record_episode

SCRIPT = "\n\n".join(
    " ".join(f"w{paragraph}x{word}" for word in range(60)) for paragraph in range(9)
)


class FakeAzure:
    def __init__(self):
        self.calls = []
        self.ssml = ""
        self.spoken = ""
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._transcribe))

    def post(self, url, data):
        self.calls.append(url)
        self.ssml = data.decode()
        self.spoken = re.sub(r"<[^>]+>", "", self.ssml)
        seconds = len(self.spoken.split()) / 150 * 60
        return SimpleNamespace(ok=True, content=b"\x00\x00" * int(24_000 * seconds))

    def _transcribe(self, **request):
        self.calls.append(request["model"])
        return SimpleNamespace(text=self.spoken)


@pytest.fixture
def azure(monkeypatch):
    fake = FakeAzure()
    monkeypatch.setattr(
        requests.Session, "post", lambda session, url, data, **request: fake.post(url, data)
    )
    return fake


def test_episode_is_recorded_and_checked(azure, tmp_path):
    speaker = Speaker(
        Foundry(azure, "https://test/", dict), "MAI-Voice-2.1", "en-US-Olivia", "", "stt"
    )
    record_episode(speaker, SCRIPT, tmp_path / "episode.mp3")
    assert (tmp_path / "episode.mp3").exists()
    assert azure.calls == ["https://test/tts/cognitiveservices/v1", "stt", "stt"]


def test_pronunciations_keep_the_ssml_valid(azure):
    pronunciations = {"Nginx": "engine x", "engine": "EN-jin", "AI": "A I"}
    foundry = Foundry(azure, "https://test/", dict)
    foundry.speak("MAI-Voice-2.1", "en-US-Olivia", "", pronunciations, "Nginx & OpenAI, an engine.")
    subs = ET.fromstring(azure.ssml).iter("{http://www.w3.org/2001/10/synthesis}sub")
    assert [sub.get("alias") for sub in subs] == ["engine x", "EN-jin"]
