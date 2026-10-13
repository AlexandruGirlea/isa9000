---
title: CLI and Python
nav_order: 3
---

# CLI and Python

Global options go before the command:
`isa9000 [--config PATH] [--progress text|json] COMMAND`.
`--config` defaults to `./isa9000.toml`, then `~/.config/isa9000/config.toml`;
the `ISA9000_CONFIG` environment variable works too.

| Command | What it does |
|---|---|
| `init [PATH] [--force]` | Writes a starter `isa9000.toml`, and warns if git would commit it. |
| `check SOURCE...` | Checks that links, files and folders can be read, without calling a model. |
| `create -r REQUEST -s SOURCE...` | Creates a podcast. See below. |
| `record FOLDER` | Records the episodes that have no audio yet. See below. |
| `cover FOLDER` | Draws new cover art. |
| `site [--serve] [--port N]` | Builds the website, and optionally previews it at `http://127.0.0.1:8800`. `--audio-kb` and `--output` override the folders. |
| `ui [--port N] [--no-browser]` | Opens the [studio](ui.md). |

## create

```bash
isa9000 create -r "What changed in our travel policy?" -s ./policies -s https://intranet.example.com/travel
```

| Flag | Meaning |
|---|---|
| `-r, --request` | What the podcast should cover. |
| `-s, --source` | A link, file or folder. Repeat for more. |
| `--audio-kb` | The audio knowledge base folder to create the podcast in. Default: `[output] folder`. |
| `--text-only` | Write, fact-check and polish the transcripts, then stop. |
| `--follow-links` | Also read up to 25 linked pages from the same section of each website. |

## record

```bash
isa9000 record "isa9000-audio_kb/2026-10-13 - Travel Policy"               # what is missing
isa9000 record "isa9000-audio_kb/2026-10-13 - Travel Policy" --episode 3   # one episode again
```

| Flag | Meaning |
|---|---|
| `-e, --episode N` | Record only this episode again. Repeat for more. |
| `--force` | Record every episode again. |
| `--chunked` | Record in parts of four paragraphs, for an episode that keeps failing its check. |

After recording, rebuild the website: see [Website and publishing](publishing.md).

## Output

```text
isa9000-audio_kb/
├── .gitignore                    keeps internal content out of git
└── 2026-10-13 - Travel Policy/
    ├── 01 - What Changed.mp3
    ├── 01 - What Changed.txt
    ├── cover.jpg
    └── podcast.json              request, sources, models, review scores, notes
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | The run failed: a source, an API call or a recording |
| `2` | Configuration or input problem |
| `3` | `create` stopped before recording: the podcast needs review |
| `130` | Interrupted |

`--progress json` prints one JSON object per line, for other tools:
`{"stage": "write", "message": "Writing episode 2/5: ...", "current": 2, "total": 5}`.
Stages: `check`, `read`, `plan`, `write`, `verify`, `review`, `record`, `site`,
`done`, `error`. The line that starts a podcast also carries its `folder`.

## Python

```python
from isa9000 import create_podcast, load_config, record_podcast
from isa9000.podcast import cover_podcast
from isa9000.site import build_site

config = load_config("isa9000.toml")
result = create_podcast("What changed in our travel policy?", ["./policies"], config=config)
if not result.approved:
    print("Needs review:", result.notes)
record_podcast(result.folder, config, episodes={2})  # one episode again
build_site(config)
```

| Function | Notes |
|---|---|
| `create_podcast(request, sources, config=None, podcasts=None, audio=True, progress=print, follow_links=False)` | Returns a `PodcastResult`: `title`, `folder`, `episodes`, `approved`, `notes`. |
| `record_podcast(folder, config=None, progress=print, force=False, episodes=None, chunked=False)` | Returns a `PodcastResult`. |
| `cover_podcast(folder, config=None, progress=print)` | Returns the cover's path. |
| `build_site(config=None, podcasts=None, output=None, progress=print)` | Returns the website folder. |

`progress` receives a `Step` with `stage`, `message`, `current`, `total` and
`folder`, the same as `--progress json`. Errors: `ConfigError` (configuration
or credentials), `SourceError` (unreadable sources, with `statuses`),
`ValueError` (empty request, unknown episode), `SpeechError` (a recording failed
its checks).
