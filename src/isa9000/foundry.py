from __future__ import annotations

import base64
import re
from xml.sax.saxutils import escape, quoteattr

import openai
import requests
from pydantic import BaseModel
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from isa9000.config import REQUEST_TIMEOUT_MS, RETRY_ATTEMPTS
from isa9000.voice import SAMPLE_RATE, SpeechError

REASONING = {"effort": "medium"}
SPEECH_HEADERS = {
    "Content-Type": "application/ssml+xml",
    "X-Microsoft-OutputFormat": "raw-24khz-16bit-mono-pcm",
}


class Foundry:
    def __init__(self, client, endpoint: str, auth) -> None:
        self.client = client
        self.speech_url = f"{endpoint.rstrip('/')}/tts/cognitiveservices/v1"
        self.auth = auth
        retry = Retry(
            total=RETRY_ATTEMPTS,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=None,
            raise_on_status=False,
        )
        self.speech = requests.Session()
        self.speech.mount("https://", HTTPAdapter(max_retries=retry))

    def structured(self, model: str, prompt: str, schema: type[BaseModel]):
        response = self.client.responses.parse(
            model=model, input=prompt, text_format=schema, reasoning=REASONING
        )
        if response.output_parsed is None:
            raise RuntimeError(f"{model} returned no usable answer: {response.output_text[:200]}")
        return response.output_parsed

    def text(self, model: str, prompt: str | list) -> str:
        response = self.client.responses.create(model=model, input=prompt, reasoning=REASONING)
        return response.output_text

    def read_pdf(self, model: str, data: bytes, prompt: str) -> str:
        pdf = f"data:application/pdf;base64,{base64.b64encode(data).decode()}"
        content = [
            {"type": "input_file", "filename": "source.pdf", "file_data": pdf},
            {"type": "input_text", "text": prompt},
        ]
        try:
            return self.text(model, [{"role": "user", "content": content}])
        except openai.BadRequestError:
            return ""

    def speak(
        self, model: str, voice: str, style: str, pronunciations: dict[str, str], text: str
    ) -> tuple[bytes, int]:
        body = escape(text)
        if pronunciations:
            aliases = {escape(term): quoteattr(spoken) for term, spoken in pronunciations.items()}
            terms = "|".join(map(re.escape, sorted(aliases, key=len, reverse=True)))
            body = re.sub(
                rf"(?<!\w)(?:{terms})(?!\w)",
                lambda match: f"<sub alias={aliases[match[0]]}>{match[0]}</sub>",
                body,
            )
        name = quoteattr(f"{voice}:{model}")
        ssml = (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
            f"<voice name={name}>{body}</voice></speak>"
        )
        response = self.speech.post(
            self.speech_url,
            headers={**SPEECH_HEADERS, **self.auth()},
            data=ssml.encode(),
            timeout=REQUEST_TIMEOUT_MS / 1000,
        )
        if not response.ok:
            raise SpeechError(f"{model} failed: {response.status_code} {response.text[:200]}")
        if not response.content:
            raise SpeechError(f"{model} returned no audio")
        return response.content, SAMPLE_RATE

    def transcribe(self, model: str, wav: bytes) -> str:
        return self.client.audio.transcriptions.create(model=model, file=("clip.wav", wav)).text

    def draw(self, model: str, prompt: str) -> tuple[bytes, str]:
        response = self.client.images.generate(model=model, prompt=prompt, size="1024x1024")
        image = response.data[0].b64_json if response.data else None
        if not image:
            raise RuntimeError(f"{model} returned no cover image")
        data = base64.b64decode(image)
        return data, ".png" if data.startswith(b"\x89PNG") else ".jpg"
