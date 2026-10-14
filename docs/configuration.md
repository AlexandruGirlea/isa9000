---
title: Configuration
nav_order: 4
---

# Configuration

Everything is set in `isa9000.toml`. `isa9000 init` writes one with every
setting and a comment for each. Relative paths are resolved from the file's
folder. The file can hold credentials: keep it out of version control, or commit
it without them.

`provider` at the top of the file chooses the AI service: `"azure"` (the
default: Microsoft Foundry) or `"google"` (the Gemini API or Vertex AI). A file
without `provider` that sets Gemini models or `[google]` credentials, such as
one written by isa9000 0.1, uses Google.

## azure

| Setting | Default | Meaning |
|---|---|---|
| `endpoint` | `""` | The endpoint of your Microsoft Foundry resource (not of a project), for example `https://my-resource.openai.azure.com/`. Empty uses `AZURE_OPENAI_ENDPOINT`. |
| `api_key` | `""` | An API key of the resource. Empty uses `AZURE_OPENAI_API_KEY`, or else `az login` with the Foundry User role on the resource. |

## google

| Setting | Default | Meaning |
|---|---|---|
| `api_key` | `""` | A [Gemini API key](https://aistudio.google.com/apikey). Empty uses `GEMINI_API_KEY` or `GOOGLE_API_KEY`. |
| `project` | `""` | A Google Cloud project for Vertex AI. When set, `api_key` is ignored. |
| `location` | `"global"` | The Vertex AI location. |
| `credentials_file` | `""` | A service-account key for Vertex AI. Empty uses `gcloud auth application-default login`. |

## models

Empty settings use the default of your provider. On Azure, `text`, `image` and
`transcribe` are the names of your deployments in the Foundry resource, and
`speech` is an Azure Speech voice model. `text` must be a reasoning model, such
as GPT-5 or newer. Swap in newer models here as you deploy them.

| Setting | Azure default | Google default | Used for |
|---|---|---|---|
| `text` | `"gpt-6.1-sol"` | `"gemini-3.1-pro-preview"` | Reading PDFs, planning, writing, checking |
| `speech` | `"MAI-Voice-2.1"` | `"gemini-2.5-pro-preview-tts"` | Narration |
| `image` | `"gpt-image-2.5-sunburst"` | `"gemini-3-pro-image"` | Cover art |
| `transcribe` | `"gpt-transcribe"` | The `text` model | Checking each recording |

## narrator

| Setting | Default | Meaning |
|---|---|---|
| `name` | `"Isabela"` | The name in the greeting. |
| `voice` | `""` | Empty uses `"en-US-Olivia"` on Azure and `"Kore"` on Google. Others to try: en-US-Harper or en-US-Iris on Azure; Sulafat, Aoede, Leda or Zephyr on Google. |
| `style` | `"Read the script below like a professional podcaster, with a warm, engaging, and slightly energetic tone."` | How the voice reads, on Gemini. Azure Speech voices take the tone from the script. |

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
| `accent_color` | `"#6C3CE1"` | The brand colour of the audio generation UI and the presentation website. |
| `logo` | `""` | An SVG, PNG or JPG. Empty uses the isa9000 logo. |

Greetings and endings can use `{narrator}`, `{brand}`, `{podcast}`, `{episode}`,
`{episodes}`, `{title}` and `{powered_by}`.

## output

| Setting | Default | Meaning |
|---|---|---|
| `folder` | `"isa9000-audio_kb"` | Where podcasts are saved. |
| `fact_check` | `true` | Check every claim against its sources. |

## presentation_website

| Setting | Default | Meaning |
|---|---|---|
| `folder` | `"isa9000-presentation_website"` | Where the presentation website is built. |
| `base_url` | `""` | The presentation website's address; needed for podcast feeds. |
| `title` | `""` | The name in the navigation bar. Empty uses `brand`. |
| `heading` | `"Internal Audio Knowledge Base"` | The home-page heading. |
| `description` | `"AI-generated podcasts that keep the team up to date."` | The line under it. |
