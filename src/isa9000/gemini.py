from __future__ import annotations

import io
import wave

from google.genai import types
from pydantic import BaseModel

from isa9000.voice import SAMPLE_RATE, SpeechError, VoiceRefused

VERBATIM = (
    "CRITICAL: You MUST read the ENTIRE script verbatim, from the first word to the last word, "
    "in the exact order it appears. Do NOT skip any sentences, paragraphs, or sections. Do NOT "
    "summarize, paraphrase, compress, or jump ahead. Do NOT shorten the content. Every single "
    "word between [SCRIPT TO READ ALOUD] and the end of the prompt must be spoken. If you "
    "truncate the reading, the output is invalid."
)


def _instructions(style: str, pronunciations: dict[str, str]) -> str:
    lines = ["[INSTRUCTIONS]", f"Style: {style}", VERBATIM]
    if pronunciations:
        pairs = "; ".join(f"{term} -> {spoken}" for term, spoken in pronunciations.items())
        lines.append(f"Pronunciations: {pairs}")
    lines += ["Do not read these instructions aloud.", "[END INSTRUCTIONS]"]
    return "\n".join(lines) + "\n\n[SCRIPT TO READ ALOUD]\n"


def _pcm(data: bytes) -> tuple[bytes, int]:
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data)) as wav:
            return wav.readframes(wav.getnframes()), wav.getframerate()
    return data, SAMPLE_RATE


class Gemini:
    def __init__(self, client) -> None:
        self.client = client

    def structured(self, model: str, prompt: str, schema: type[BaseModel]):
        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        if response.parsed is None:
            raise RuntimeError(f"{model} returned no usable answer: {(response.text or '')[:200]}")
        return response.parsed

    def text(self, model: str, prompt: str) -> str:
        return self.client.models.generate_content(model=model, contents=prompt).text or ""

    def read_pdf(self, model: str, data: bytes, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=data, mime_type="application/pdf"), prompt],
        )
        return response.text or ""

    def speak(
        self, model: str, voice: str, style: str, pronunciations: dict[str, str], text: str
    ) -> tuple[bytes, int]:
        response = self.client.models.generate_content(
            model=model,
            contents=_instructions(style, pronunciations) + text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                ),
            ),
        )
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            # No content at all means the voice's safety filter refused the wording.
            reason = getattr(candidate, "finish_reason", None) if candidate else "no candidates"
            raise VoiceRefused(f"{model} refused to read the script (finish reason: {reason})")
        for part in candidate.content.parts or []:
            if part.inline_data and part.inline_data.data:
                return _pcm(part.inline_data.data)
        raise SpeechError(f"{model} returned no audio")

    def transcribe(self, model: str, wav: bytes) -> str:
        response = self.client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=wav, mime_type="audio/wav"),
                "Transcribe this audio verbatim. Output only the transcript.",
            ],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="LOW")
            ),
        )
        return response.text or ""

    def draw(self, model: str, prompt: str) -> tuple[bytes, str]:
        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="1:1"),
            ),
        )
        part = next((p for p in response.parts or [] if p.inline_data and p.inline_data.data), None)
        if part is None:
            raise RuntimeError(f"{model} returned no cover image")
        extension = ".png" if "png" in (part.inline_data.mime_type or "") else ".jpg"
        return part.inline_data.data, extension
