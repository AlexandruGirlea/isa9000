# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [semantic versioning](https://semver.org/).

## 0.2.0

- Microsoft Foundry on Azure is now the default AI service: GPT-6.1 Sol writes
  and checks, the Azure Speech voice Olivia (MAI-Voice-2.1) narrates, GPT Image
  2.5 Sunburst draws covers and gpt-transcribe checks each recording. Set your
  Foundry `[azure] endpoint`, and sign in with an API key or with `az login`.
- Google stays fully supported with `provider = "google"`. A configuration
  file without `provider` that sets Gemini models or `[google]` credentials,
  such as one written by 0.1.x, keeps using Google unchanged.
- `[models] transcribe` names the model that checks each recording: by default
  gpt-transcribe on Azure and the text model on Google. Empty model and voice
  settings use the default of the provider.
- Upgrading from 0.1.x: a Google setup with no configuration file, using only
  `GEMINI_API_KEY` or `GOOGLE_API_KEY`, now needs an `isa9000.toml` with
  `provider = "google"` at the top. To move a 0.1.x file to Azure, set
  `provider = "azure"` and empty its `[models]` and `[narrator] voice`, or run
  `isa9000 init --force`.
- New dependencies: `openai` and `azure-identity`.

## 0.1.1

- Clearer names. The browser app that creates podcasts is now
  `isa9000 audio-generation-ui`, installed with `isa9000[audio-generation-ui]`
  (was `isa9000 ui` and `isa9000[ui]`). The website where people listen is now
  `isa9000 presentation-website`, with a `[presentation_website]` section in
  `isa9000.toml`, an `isa9000-presentation_website` folder and
  `isa9000.presentation_website.build_presentation_website` in Python (was
  `site`).
- Upgrading from 0.1.0: rename `[site]` to `[presentation_website]` in
  `isa9000.toml`. The old `isa9000-site` folder can be deleted.

## 0.1.0

First release.

- Create short internal podcasts from links, files and folders: written only
  from those sources, fact-checked, scored as a listener would hear them,
  narrated with a Gemini voice and given cover art.
- A local studio to create, review and re-record podcasts, plus a command line
  and a Python library for automation.
- A static knowledge base website with search, transcripts and podcast feeds,
  and GitHub Actions examples that publish it on every change.
- White-label: narrator, voice, greetings, brand, colour and logo are settings.
