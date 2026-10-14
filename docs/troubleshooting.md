---
title: Troubleshooting
nav_order: 7
---

# Troubleshooting

| Problem | What to do |
|---|---|
| "no Google credentials" | Set `[google] api_key` or `project` in `isa9000.toml`, or `GEMINI_API_KEY`. Pass `--config` to be sure which file is used. |
| "no Azure endpoint" | Set `[azure] endpoint` in `isa9000.toml`, or `AZURE_OPENAI_ENDPOINT`. To use Google, add `provider = "google"` at the top of `isa9000.toml`. |
| "DefaultAzureCredential failed to retrieve a token" | Run `az login`, or set `[azure] api_key`. |
| `DeploymentNotFound` on Azure | A name in `[models]` is not a deployment in your Foundry resource, or the deployment is only a few minutes old. |
| `401` or `PermissionDenied` on Azure | Without an API key, your account needs the Foundry User role on the resource. Run `az login` again. |
| `InsufficientQuota` when deploying on Azure | Request quota for the model in the Foundry portal, under **Manage**, then **Quota**. |
| A source says *Access refused* | It needs a sign-in. Use a synced folder or an exported HTML or PDF copy. |
| *Not found* or *Error page* | Open the link in a browser and copy the exact address. |
| `too_little_text` | The page builds its content with JavaScript. Save it as HTML or PDF and use the file. |
| "needs review before recording" (exit code `3`) | Read the reasons in `podcast.json` or the audio generation UI. Fix the sources or the request and create it again, or record it anyway with `isa9000 record`. |
| "failed its audio check" | Re-record that episode: **Re-record** in the audio generation UI, or `isa9000 record FOLDER --episode N`, adding `--chunked` if it keeps failing. |
| "the voice refused the original wording" | The script was rephrased and recorded. Read the new transcript before publishing. |
| The narrator says a name wrong | Add it to `[narrator.pronunciations]` and re-record the episode. |
| The player cannot seek | The host does not answer byte-range requests. Preview with `isa9000 presentation-website --serve`. |
| Rate limits or quota errors | isa9000 retries six times with growing pauses. Raise the quota, or run fewer podcasts at once. |
| "not empty and was not created by isa9000" | The `[presentation_website] folder` holds other files. Choose another folder. |
| A button in the audio generation UI does nothing | It may be running an older version. Restart it. |
| The port is in use | `isa9000 audio-generation-ui --port 8791` or `isa9000 presentation-website --serve --port 8801`. |
