# Contributing

## Setup

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check .
uv build
```

Python 3.11 or newer, on Linux or macOS. Creating podcasts needs Google
credentials; see [docs/configuration.md](docs/configuration.md). The tests, linting and
building do not: the tests use an offline stand-in for Gemini.

## Pull requests

- One change per PR, with a note on why.
- `pytest` and `ruff check .` must pass and the package must build; CI runs them
  on Python 3.11 to 3.13. New behaviour ships with a test in the same PR.
- Quality changes (prompts, review thresholds, audio checks) are judged on real
  podcasts, not on lint. Open an issue first, and include before and after
  transcripts or recordings made from public sources.
- User-facing changes update the documentation in [docs/](docs/) in the same
  PR. GitHub Pages publishes it from that folder.

## Reporting a wrong or weak podcast

Include the request, the sources, `podcast.json`, and what you expected. A claim
the sources do not support is a higher-priority bug than an episode that is
merely dull.

Do not paste confidential or personal data into an issue. Reproduce the problem
with public sources wherever you can.

## Licensing of contributions

This project is open source under the Apache License 2.0. Contributions are
accepted on the same terms: as set out in section 5 of that license, any
contribution you intentionally submit for inclusion is licensed under
Apache-2.0, without any additional terms. No separate contributor licence
agreement is required.

Only submit work you have the right to contribute. Do not submit code, data or
text owned by an employer or a client unless you are permitted to do so.

## Disclaimer

isa9000 is provided as is, without warranty or condition of any kind. Its
podcasts are written and checked by AI models; review important podcasts before
you publish them. See [LICENSE](LICENSE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
