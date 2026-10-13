from __future__ import annotations

import difflib
import io
import re
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import lameenc
from google.genai import types

SAMPLE_RATE = 24_000
PARAGRAPHS_PER_CHUNK = 4
CHUNK_GAP_MS = 250
ATTEMPTS = 3
SYNTHESIS_WPM = 140
SYNTHESIS_RANGE = (0.5, 1.6)
BASELINE_WPM = 150
LENGTH_WINDOW = (0.85, 1.30)
SPOT_CHECK_SECONDS = 30
SPOT_CHECK_WORDS = 25
SPOT_CHECK_MIN_HEARD = 0.7
VERBATIM = (
    "CRITICAL: You MUST read the ENTIRE script verbatim, from the first word to the last word, "
    "in the exact order it appears. Do NOT skip any sentences, paragraphs, or sections. Do NOT "
    "summarize, paraphrase, compress, or jump ahead. Do NOT shorten the content. Every single "
    "word between [SCRIPT TO READ ALOUD] and the end of the prompt must be spoken. If you "
    "truncate the reading, the output is invalid."
)


class SpeechError(RuntimeError):
    pass


class VoiceRefused(SpeechError):
    pass


@dataclass
class Speaker:
    client: object
    model: str
    voice: str
    style: str
    check_model: str
    pronunciations: dict[str, str] = field(default_factory=dict)


def _instructions(speaker: Speaker) -> str:
    lines = ["[INSTRUCTIONS]", f"Style: {speaker.style}", VERBATIM]
    if speaker.pronunciations:
        pairs = "; ".join(f"{term} -> {spoken}" for term, spoken in speaker.pronunciations.items())
        lines.append(f"Pronunciations: {pairs}")
    lines += ["Do not read these instructions aloud.", "[END INSTRUCTIONS]"]
    return "\n".join(lines) + "\n\n[SCRIPT TO READ ALOUD]\n"


def _pcm(data: bytes) -> tuple[bytes, int]:
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data)) as wav:
            return wav.readframes(wav.getnframes()), wav.getframerate()
    return data, SAMPLE_RATE


def _wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _speak(speaker: Speaker, text: str) -> tuple[bytes, int]:
    response = speaker.client.models.generate_content(
        model=speaker.model,
        contents=_instructions(speaker) + text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=speaker.voice)
                )
            ),
        ),
    )
    candidate = response.candidates[0] if response.candidates else None
    if candidate is None or candidate.content is None:
        # No content at all means the voice's safety filter refused the wording.
        reason = getattr(candidate, "finish_reason", None) if candidate else "no candidates"
        raise VoiceRefused(f"{speaker.model} refused to read the script (finish reason: {reason})")
    for part in candidate.content.parts or []:
        if part.inline_data and part.inline_data.data:
            return _pcm(part.inline_data.data)
    raise SpeechError(f"{speaker.model} returned no audio")


def _chunks(text: str, chunked: bool) -> list[str]:
    if not chunked:
        return [text.strip()] if text.strip() else []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [
        "\n\n".join(paragraphs[start : start + PARAGRAPHS_PER_CHUNK])
        for start in range(0, len(paragraphs), PARAGRAPHS_PER_CHUNK)
    ]


def _speak_checked(speaker: Speaker, text: str) -> tuple[bytes, int]:
    # Text-to-speech occasionally stops early or rambles; a clip far off the expected length
    # is recorded again.
    expected = len(text.split()) / SYNTHESIS_WPM * 60
    low, high = SYNTHESIS_RANGE
    seconds = 0.0
    for _ in range(ATTEMPTS):
        pcm, rate = _speak(speaker, text)
        seconds = len(pcm) / (2 * rate)
        if low * expected <= seconds <= high * expected:
            return pcm, rate
    raise SpeechError(
        f"audio length stayed off after {ATTEMPTS} attempts "
        f"({seconds:.0f}s for about {expected:.0f}s of text)"
    )


def synthesize(speaker: Speaker, text: str, chunked: bool = False) -> tuple[bytes, int]:
    pieces = [_speak_checked(speaker, chunk) for chunk in _chunks(text, chunked)]
    if not pieces:
        raise SpeechError("nothing to read")
    rate = pieces[0][1]
    gap = b"\x00\x00" * (rate * CHUNK_GAP_MS // 1000)
    return gap.join(pcm for pcm, _ in pieces), rate


def _spoken_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _share_heard(expected: list[str], heard: list[str]) -> float:
    matcher = difflib.SequenceMatcher(None, expected, heard, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / max(len(expected), 1)


def _transcribe(speaker: Speaker, pcm: bytes, rate: int) -> list[str]:
    response = speaker.client.models.generate_content(
        model=speaker.check_model,
        contents=[
            types.Part.from_bytes(data=_wav(pcm, rate), mime_type="audio/wav"),
            "Transcribe this audio verbatim. Output only the transcript.",
        ],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="LOW")
        ),
    )
    return _spoken_words(response.text or "")


def _off_length(text: str, pcm: bytes, rate: int) -> str:
    seconds = len(pcm) / (2 * rate)
    expected = len(text.split()) / BASELINE_WPM * 60
    low, high = LENGTH_WINDOW
    if low * expected <= seconds <= high * expected:
        return ""
    return f"{seconds:.0f}s of audio for about {expected:.0f}s of text"


def _misheard(speaker: Speaker, text: str, pcm: bytes, rate: int) -> str:
    words = _spoken_words(text)
    clip = SPOT_CHECK_SECONDS * rate * 2
    opening = _share_heard(words[:SPOT_CHECK_WORDS], _transcribe(speaker, pcm[:clip], rate))
    closing = _share_heard(words[-SPOT_CHECK_WORDS:], _transcribe(speaker, pcm[-clip:], rate))
    if min(opening, closing) >= SPOT_CHECK_MIN_HEARD:
        return ""
    return f"heard {opening:.0%} of the opening words and {closing:.0%} of the closing words"


def to_mp3(pcm: bytes, rate: int, path: Path, bitrate: int = 128) -> None:
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    path.write_bytes(encoder.encode(pcm) + encoder.flush())


def _problems(speaker: Speaker, text: str, pcm: bytes, rate: int) -> list[str]:
    return [p for p in (_off_length(text, pcm, rate), _misheard(speaker, text, pcm, rate)) if p]


def record_episode(
    speaker: Speaker,
    text: str,
    path: Path,
    on_retry: Callable[[list[str]], None] = lambda problems: None,
    chunked: bool = False,
) -> float:
    # A take must be close to the length its text needs and must start and end with the script's
    # words. Otherwise it is recorded again in shorter parts, once.
    pcm, rate = synthesize(speaker, text, chunked)
    problems = _problems(speaker, text, pcm, rate)
    if problems:
        on_retry(problems)
        pcm, rate = synthesize(speaker, text, chunked=True)
        problems = _problems(speaker, text, pcm, rate)
        if problems:
            raise SpeechError(f"{path.name} failed its audio check: {'; '.join(problems)}")
    to_mp3(pcm, rate, path)
    return len(pcm) / (2 * rate)
