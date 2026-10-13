from types import SimpleNamespace

import pytest

from isa9000 import podcast, writer

WORDS_PER_MINUTE = 150
RATE = 24_000


class FakeGemini:
    def __init__(self):
        self.calls = []
        self.scores = [9]
        self.problems = [[]]
        self.stretch = 1.0
        self.refusals = 0
        self.spoken = ""
        self.heard = None
        self.models = self

    def generate_content(self, model, contents, config=None):
        modalities = getattr(config, "response_modalities", None)
        schema = getattr(config, "response_schema", None)
        if modalities == ["IMAGE"]:
            return self._image()
        if modalities == ["AUDIO"]:
            return self._speech(contents)
        if isinstance(contents, list):
            self.calls.append("transcribe")
            return SimpleNamespace(text=self.spoken if self.heard is None else self.heard)
        if schema is writer.PodcastPlan:
            return self._parsed("plan", self._plan())
        if schema is writer.TitleScore:
            return self._parsed("title", writer.TitleScore(score=9, reason="clear", suggestions=[]))
        if schema is writer.Review:
            problems = self.problems.pop(0) if len(self.problems) > 1 else self.problems[0]
            return self._parsed("review", writer.Review(problems=problems))
        if schema is writer.PodcastScore:
            return self._parsed("score", self._score())
        self.calls.append("write")
        return SimpleNamespace(text=" ".join(["word"] * 520))

    def _parsed(self, call, value):
        self.calls.append(call)
        return SimpleNamespace(parsed=value, text="")

    def _plan(self):
        episodes = [
            writer.EpisodePlan(
                title=f"Episode {n}",
                summary=f"Summary {n}.",
                focus="focus",
                excludes="other things",
                key_points=["a fact"],
                misconception="",
                example=f"example {n}",
                hook="hook",
                sources=[1],
            )
            for n in (1, 2)
        ]
        return writer.PodcastPlan(
            title="Expense Policy Changes",
            description="What changed.",
            cover="Green, receipt icon",
            episodes=episodes,
        )

    def _score(self):
        score = self.scores.pop(0) if len(self.scores) > 1 else self.scores[0]
        episodes = [
            writer.EpisodeScore(
                episode_number=n, score=score, strengths="clear", issues="dense", suggestion="split"
            )
            for n in (1, 2)
        ]
        return writer.PodcastScore(
            overall_score=score,
            flow_score=9,
            flow_issues="None",
            flow_suggestion="None",
            summary="ok",
            episodes=episodes,
        )

    def _speech(self, contents):
        self.calls.append("speech")
        text = contents.split("[SCRIPT TO READ ALOUD]\n", 1)[1]
        self.spoken = text
        if self.refusals:
            self.refusals -= 1
            return SimpleNamespace(
                candidates=[SimpleNamespace(content=None, finish_reason="PROHIBITED_CONTENT")]
            )
        seconds = len(text.split()) / WORDS_PER_MINUTE * 60 * self.stretch
        audio = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x00\x00" * int(RATE * seconds)))
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[audio]))])

    def _image(self):
        self.calls.append("image")
        image = SimpleNamespace(
            inline_data=SimpleNamespace(data=b"\x89PNG fake", mime_type="image/png")
        )
        return SimpleNamespace(parts=[image])


@pytest.fixture
def gemini(monkeypatch):
    fake = FakeGemini()
    monkeypatch.setattr(podcast, "genai_client", lambda config: fake)
    monkeypatch.setattr(podcast, "WORKERS", 1)
    return fake


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "policy.md"
    path.write_text("Expense claims must be filed within 60 days. " * 30)
    return path
