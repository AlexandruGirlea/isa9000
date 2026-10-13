---
title: Troubleshooting
nav_order: 7
---

# Troubleshooting

| Problem | What to do |
|---|---|
| "no Google credentials" | Set `[google] api_key` or `project` in `isa9000.toml`, or `GEMINI_API_KEY`. Pass `--config` to be sure which file is used. |
| A source says *Access refused* | It needs a sign-in. Use a synced folder or an exported HTML or PDF copy. |
| *Not found* or *Error page* | Open the link in a browser and copy the exact address. |
| `too_little_text` | The page builds its content with JavaScript. Save it as HTML or PDF and use the file. |
| "needs review before recording" (exit code `3`) | Read the reasons in `podcast.json` or the studio. Fix the sources or the request and create it again, or record it anyway with `isa9000 record`. |
| "failed its audio check" | Re-record that episode: **Re-record** in the studio, or `isa9000 record FOLDER --episode N`, adding `--chunked` if it keeps failing. |
| "the voice refused the original wording" | The script was rephrased and recorded. Read the new transcript before publishing. |
| The narrator says a name wrong | Add it to `[narrator.pronunciations]` and re-record the episode. |
| The player cannot seek | The host does not answer byte-range requests. Preview with `isa9000 site --serve`. |
| Rate limits or quota errors | isa9000 retries six times with growing pauses. Raise the quota, or run fewer podcasts at once. |
| "not empty and was not created by isa9000" | The `[site] folder` holds other files. Choose another folder. |
| A button in the studio does nothing | The studio may be running an older version. Restart it. |
| The port is in use | `isa9000 ui --port 8791` or `isa9000 site --serve --port 8801`. |
