---
title: Configuration
nav_order: 4
---

# Configuration

Everything is set in `isa9000.toml`. `isa9000 init` writes one with every
setting and a comment for each. Relative paths are resolved from the file's
folder. The file can hold credentials: keep it out of version control, or commit
it without them.

## google

| Setting | Default | Meaning |
|---|---|---|
| `api_key` | `""` | A [Gemini API key](https://aistudio.google.com/apikey). Empty uses `GEMINI_API_KEY` or `GOOGLE_API_KEY`. |
| `project` | `""` | A Google Cloud project for Vertex AI. When set, `api_key` is ignored. |
| `location` | `"global"` | The Vertex AI location. |
| `credentials_file` | `""` | A service-account key for Vertex AI. Empty uses `gcloud auth application-default login`. |

## models

| Setting | Default | Used for |
|---|---|---|
| `text` | `"gemini-3.1-pro-preview"` | Reading PDFs, planning, writing, checking |
| `speech` | `"gemini-2.5-pro-preview-tts"` | Narration |
| `image` | `"gemini-3-pro-image"` | Cover art |

## narrator

| Setting | Default | Meaning |
|---|---|---|
| `name` | `"Isabela"` | The name in the greeting. |
| `voice` | `"Kore"` | Any Gemini voice, for example Sulafat, Aoede, Leda or Zephyr. |
| `style` | `"Read the script below like a professional podcaster, with a warm, engaging, and slightly energetic tone."` | How the voice reads. |

Names the voice gets wrong go in `[narrator.pronunciations]`:

```toml
[narrator.pronunciations]
"Nginx" = "engine x"
```

## branding

| Setting | Default | Meaning |
|---|---|---|
| `brand` | `"isa9000"` | The brand name, also written small on covers. |
| `powered_by` | `"Powered by girlea.ro"` | Attribution; `""` removes it. |
| `greeting` | `"Hi, I'm {narrator}. This is {podcast}, episode {episode} of {episodes}: {title}."` | Spoken at the start of every episode. |
| `ending`, `final_ending` | Short sign-offs | Spoken at the end; the last episode uses `final_ending`. |
| `accent_color` | `"#6C3CE1"` | The brand colour of the studio and the website. |
| `logo` | `""` | An SVG, PNG or JPG. Empty uses the isa9000 logo. |

Greetings and endings can use `{narrator}`, `{brand}`, `{podcast}`, `{episode}`,
`{episodes}`, `{title}` and `{powered_by}`.

## output

| Setting | Default | Meaning |
|---|---|---|
| `folder` | `"isa9000-audio_kb"` | Where podcasts are saved. |
| `fact_check` | `true` | Check every claim against its sources. |

## site

| Setting | Default | Meaning |
|---|---|---|
| `folder` | `"isa9000-site"` | Where the website is built. |
| `base_url` | `""` | The website's address; needed for podcast feeds. |
| `title` | `""` | The name in the navigation bar. Empty uses `brand`. |
| `heading` | `"Internal Audio Knowledge Base"` | The home-page heading. |
| `description` | `"AI-generated podcasts that keep the team up to date."` | The line under it. |
