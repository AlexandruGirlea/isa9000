from __future__ import annotations

import os
import string
import subprocess
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CONFIG_NAME = "isa9000.toml"
DEFAULT_LOGO = Path(__file__).with_name("logo.png")
DEFAULT_ICON = Path(__file__).with_name("logo-64.png")
DEFAULT_MARKS = {
    "on_dark": Path(__file__).with_name("logo-mark-light.png"),
    "on_light": Path(__file__).with_name("logo-mark-dark.png"),
}
CONFIG_ENV = "ISA9000_CONFIG"
USER_CONFIG = Path.home() / ".config" / "isa9000" / "config.toml"
KEY_ENVS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
AZURE_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_KEY_ENV = "AZURE_OPENAI_API_KEY"
AZURE_SCOPE = "https://cognitiveservices.azure.com/.default"
AZURE_API_VERSION = "2025-04-01-preview"
DEFAULT_MODELS = {
    "azure": {
        "text": "gpt-6.1-sol",
        "speech": "DragonHDLatestNeural",
        "image": "gpt-image-2.5-sunburst",
        "transcribe": "gpt-transcribe",
    },
    "google": {
        "text": "gemini-3.1-pro-preview",
        "speech": "gemini-2.5-pro-preview-tts",
        "image": "gemini-3-pro-image",
    },
}
DEFAULT_VOICES = {"azure": "en-US-Serena", "google": "Kore"}
DEFAULT_COLOR = "#6C3CE1"
LOGO_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
PLACEHOLDERS = ("narrator", "brand", "podcast", "episode", "episodes", "title", "powered_by")
GIT_IGNORE_ALL = "# Created by isa9000: made from internal sources, so it stays out of git.\n*\n"
REQUEST_TIMEOUT_MS = 600_000
RETRY_ATTEMPTS = 6


class ConfigError(RuntimeError):
    pass


class _Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoogleSettings(_Settings):
    api_key: str = ""
    project: str = ""
    location: str = "global"
    credentials_file: str = ""


class AzureSettings(_Settings):
    endpoint: str = ""
    api_key: str = ""


class ModelSettings(_Settings):
    text: str = ""
    speech: str = ""
    image: str = ""
    transcribe: str = ""


class NarratorSettings(_Settings):
    name: str = "Isabela"
    voice: str = ""
    style: str = (
        "Read the script below like a professional podcaster, with a warm, engaging, "
        "and slightly energetic tone."
    )
    pronunciations: dict[str, str] = Field(default_factory=dict)


class BrandingSettings(_Settings):
    brand: str = "isa9000"
    powered_by: str = "Powered by girlea.ro"
    greeting: str = (
        "Hi, I'm {narrator}. This is {podcast}, episode {episode} of {episodes}: {title}."
    )
    ending: str = "That's it for this episode. Thanks for listening."
    final_ending: str = "That's the end of {podcast}. Thanks for listening."
    accent_color: str = DEFAULT_COLOR
    logo: str = ""

    @field_validator("greeting", "ending", "final_ending")
    @classmethod
    def _known_placeholders(cls, text: str) -> str:
        unknown = {name for _, name, _, _ in string.Formatter().parse(text) if name} - set(
            PLACEHOLDERS
        )
        if unknown:
            known = ", ".join(f"{{{name}}}" for name in PLACEHOLDERS)
            raise ValueError(f"unknown placeholder {{{min(unknown)}}}; use {known}")
        return text


class OutputSettings(_Settings):
    folder: str = "isa9000-audio_kb"
    fact_check: bool = True


class PresentationWebsiteSettings(_Settings):
    folder: str = "isa9000-presentation_website"
    base_url: str = ""
    title: str = ""
    heading: str = "Internal Audio Knowledge Base"
    description: str = "AI-generated podcasts that keep the team up to date."


class Config(_Settings):
    provider: Literal["azure", "google"] = "azure"
    google: GoogleSettings = Field(default_factory=GoogleSettings)
    azure: AzureSettings = Field(default_factory=AzureSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    narrator: NarratorSettings = Field(default_factory=NarratorSettings)
    branding: BrandingSettings = Field(default_factory=BrandingSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    presentation_website: PresentationWebsiteSettings = Field(
        default_factory=PresentationWebsiteSettings
    )
    path: Path | None = None

    @model_validator(mode="before")
    @classmethod
    def _google_without_provider(cls, data):
        if not isinstance(data, dict) or "provider" in data:
            return data
        models = dict(data.get("models") or {})
        google = dict(data.get("google") or {})
        credentials = ("api_key", "project", "credentials_file")
        if any(str(name).startswith("gemini") for name in models.values()) or any(
            google.get(key) for key in credentials
        ):
            return {**data, "provider": "google"}
        return data

    @model_validator(mode="after")
    def _provider_defaults(self) -> Config:
        models = {
            kind: getattr(self.models, kind) or name
            for kind, name in DEFAULT_MODELS[self.provider].items()
        }
        models.setdefault("transcribe", self.models.transcribe or models["text"])
        self.models = self.models.model_copy(update=models)
        voice = self.narrator.voice or DEFAULT_VOICES[self.provider]
        self.narrator = self.narrator.model_copy(update={"voice": voice})
        return self

    def resolve(self, value: str) -> Path:
        candidate = Path(value).expanduser()
        if candidate.is_absolute() or self.path is None:
            return candidate
        return self.path.parent / candidate

    @property
    def logo_file(self) -> Path:
        return self.resolve(self.branding.logo) if self.branding.logo else DEFAULT_LOGO

    @property
    def output_folder(self) -> Path:
        return self.resolve(self.output.folder)

    @property
    def presentation_website_folder(self) -> Path:
        return self.resolve(self.presentation_website.folder)


def find_config(explicit: str | Path | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"config file not found: {path}")
        return path
    if os.environ.get(CONFIG_ENV):
        return find_config(os.environ[CONFIG_ENV])
    for candidate in (Path.cwd() / CONFIG_NAME, USER_CONFIG):
        if candidate.is_file():
            return candidate
    return None


def load_config(path: str | Path | None = None) -> Config:
    found = find_config(path)
    if found is None:
        return Config()
    try:
        data = tomllib.loads(found.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{found}: {error}") from error
    data.pop("path", None)
    try:
        return Config(**data, path=found.resolve())
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()
        )
        raise ConfigError(f"{found}: {problems}") from error


def template() -> str:
    return files("isa9000").joinpath("isa9000.example.toml").read_text(encoding="utf-8")


def write_template(path: str | Path = CONFIG_NAME, force: bool = False) -> Path:
    target = Path(path).expanduser()
    if target.exists() and not force:
        raise ConfigError(f"{target} already exists (use --force to overwrite)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template(), encoding="utf-8")
    return target


def git_would_track(path: Path) -> bool:
    # `git check-ignore` exits 1 for a path inside a repository that is not ignored.
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", path.name],
            check=False,
            cwd=path.parent,
            capture_output=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 1


def _api_key(config: Config) -> str:
    if config.google.api_key:
        return config.google.api_key
    return next((os.environ[name] for name in KEY_ENVS if os.environ.get(name)), "")


def _azure_endpoint(config: Config) -> str:
    return config.azure.endpoint or os.environ.get(AZURE_ENDPOINT_ENV, "")


def credentials_problem(config: Config) -> str | None:
    if config.provider == "azure":
        if _azure_endpoint(config):
            return None
        return (
            "no Azure endpoint: set [azure] endpoint in isa9000.toml, "
            f"or the {AZURE_ENDPOINT_ENV} environment variable; "
            'to use Google, add provider = "google" at the top of isa9000.toml'
        )
    google = config.google
    if google.project:
        if google.credentials_file and not config.resolve(google.credentials_file).is_file():
            return f"credentials_file not found: {google.credentials_file}"
        return None
    if _api_key(config):
        return None
    return (
        "no Google credentials: set [google] api_key or project in isa9000.toml, "
        "or the GEMINI_API_KEY environment variable"
    )


def ai_client(config: Config):
    problem = credentials_problem(config)
    if problem:
        raise ConfigError(problem)
    if config.provider == "azure":
        return azure_client(config)
    from isa9000.gemini import Gemini

    return Gemini(genai_client(config))


def azure_client(config: Config):
    from openai import AzureOpenAI

    from isa9000.foundry import Foundry

    endpoint = _azure_endpoint(config)
    options = {
        "azure_endpoint": endpoint,
        "api_version": AZURE_API_VERSION,
        "timeout": REQUEST_TIMEOUT_MS / 1000,
        "max_retries": RETRY_ATTEMPTS,
    }
    api_key = config.azure.api_key or os.environ.get(AZURE_KEY_ENV, "")
    if api_key:
        client = AzureOpenAI(api_key=api_key, **options)
        return Foundry(client, endpoint, lambda: {"Ocp-Apim-Subscription-Key": api_key})
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    token = get_bearer_token_provider(DefaultAzureCredential(), AZURE_SCOPE)
    client = AzureOpenAI(azure_ad_token_provider=token, **options)
    return Foundry(client, endpoint, lambda: {"Authorization": f"Bearer {token()}"})


def genai_client(config: Config):
    from google import genai
    from google.genai import types

    google = config.google
    http_options = types.HttpOptions(
        timeout=REQUEST_TIMEOUT_MS,
        retry_options=types.HttpRetryOptions(
            attempts=RETRY_ATTEMPTS, initial_delay=2.0, max_delay=60.0
        ),
    )
    if not google.project:
        return genai.Client(api_key=_api_key(config), http_options=http_options)
    credentials = None
    if google.credentials_file:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            str(config.resolve(google.credentials_file)),
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    return genai.Client(
        vertexai=True,
        project=google.project,
        location=google.location,
        credentials=credentials,
        http_options=http_options,
    )


def render(text: str, **values: object) -> str:
    return text.format(**values).strip()
