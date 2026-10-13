<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/AlexandruGirlea/isa9000/main/docs/assets/img/isa9000-hero-dark.png">
    <img src="https://raw.githubusercontent.com/AlexandruGirlea/isa9000/main/docs/assets/img/isa9000-hero-light.png" alt="isa9000" width="180" height="180">
  </picture>
</p>

<h1 align="center">isa9000</h1>

<p align="center">
  <strong>Turn your organization's documents into short, fact-checked podcasts.</strong>
</p>

<p align="center">
  A private audio knowledge base that runs inside your own network, with your
  own branding.
</p>

<p align="center">
  <a href="https://pypi.org/project/isa9000/"><img src="https://img.shields.io/pypi/v/isa9000" alt="PyPI"></a>
  <a href="https://pypi.org/project/isa9000/"><img src="https://img.shields.io/pypi/pyversions/isa9000" alt="Python versions"></a>
  <a href="https://github.com/AlexandruGirlea/isa9000/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0"></a>
  <a href="https://api.reuse.software/info/github.com/AlexandruGirlea/isa9000"><img src="https://api.reuse.software/badge/github.com/AlexandruGirlea/isa9000" alt="REUSE status"></a>
</p>

<p align="center">
  <a href="https://alexandrugirlea.github.io/isa9000/"><strong>Documentation</strong></a>
  ·
  <a href="https://alexandrugirlea.github.io/isa9000/audio-generation-ui.html">Audio generation UI</a>
  ·
  <a href="https://alexandrugirlea.github.io/isa9000/cli.html">CLI and Python</a>
  ·
  <a href="https://alexandrugirlea.github.io/isa9000/publishing.html">Presentation website and publishing</a>
  ·
  <a href="https://alexandrugirlea.github.io/isa9000/quality.html">How quality is enforced</a>
</p>

<p align="center">
  If isa9000 is useful to you, please ⭐ <a href="https://github.com/AlexandruGirlea/isa9000">star the repository</a>: it helps other teams find it.
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/AlexandruGirlea/isa9000/main/docs/assets/img/presentation-website-home.png" alt="The Internal Audio Knowledge Base built by isa9000" width="900">
</p>

Developed by Isabela and Alex @ [girlea.ro](https://girlea.ro),
from the engine behind [devstories.eu](https://devstories.eu) (more than 60 audio
courses). **Powered by the [Gemini API](https://ai.google.dev/gemini-api/docs).**

## Quick start

```bash
pip install "isa9000[audio-generation-ui]"
isa9000 init                           # writes isa9000.toml: add a Gemini API key to it
isa9000 audio-generation-ui            # create podcasts in your browser at http://127.0.0.1:8790
isa9000 presentation-website --serve   # build the presentation website, preview it at http://127.0.0.1:8800
```

Python 3.11 or newer, on Linux or macOS. Servers and CI only need
`pip install isa9000`.

## How it works

1. **Create.** isa9000 reads the policies, release notes, wikis, PDFs or web
   pages you point it at, plans a short series of episodes, writes each one from
   those sources only, fact-checks every claim, rewrites episodes that a
   listener review scores below 9/10 and draws cover art. Podcasts that pass the
   [quality gate](https://alexandrugirlea.github.io/isa9000/quality.html) are
   recorded straight away; the rest wait for a person to review them.
2. **Publish.** `isa9000 presentation-website` builds a static presentation
   website from your podcasts. Host it on any internal web server or storage
   bucket, by hand or with
   [GitHub Actions](https://alexandrugirlea.github.io/isa9000/publishing.html#automate-with-github-actions).
3. **Listen.** People search, play, read transcripts and share episodes from a
   phone or a desktop.

<p align="center">
  <img src="https://raw.githubusercontent.com/AlexandruGirlea/isa9000/main/docs/assets/img/audio-generation-ui.png" alt="The isa9000 audio generation UI" width="900">
</p>

Business users create podcasts in the audio generation UI on their own computer
and download the results; developers use the command line, Python and CI.
Everything listeners hear or see, from the narrator to the logo, is a setting.

## Privacy

Only what the models need leaves your machine: your request, the content of
your sources (PDFs are sent as files), the scripts to record and short clips of
each recording for its check. It goes to the Google model endpoints you
configure: the Gemini API, or Vertex AI in your own project. The presentation
website is static files with no server code or tracking. Report vulnerabilities
privately: see [SECURITY.md](https://github.com/AlexandruGirlea/isa9000/blob/main/SECURITY.md).

## License

Apache-2.0: see [LICENSE](https://github.com/AlexandruGirlea/isa9000/blob/main/LICENSE),
[NOTICE](https://github.com/AlexandruGirlea/isa9000/blob/main/NOTICE) and
[THIRD_PARTY_NOTICES.md](https://github.com/AlexandruGirlea/isa9000/blob/main/THIRD_PARTY_NOTICES.md).
Contributions are welcome: see
[CONTRIBUTING.md](https://github.com/AlexandruGirlea/isa9000/blob/main/CONTRIBUTING.md).
Using isa9000 at your organization? Tell us through [girlea.ro](https://girlea.ro).
