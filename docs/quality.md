---
title: How quality is enforced
nav_order: 5
---

# How quality is enforced

isa9000 follows the production rules of [Dev Stories](https://devstories.eu),
adapted for every business department. Each stage guards against two failures:
saying something the sources do not say, and being hard to follow by ear.

1. **Reading.** The main content of web pages; PDFs read by Gemini so tables and
   figures survive; up to 150,000 characters per source and 600,000 in total,
   with a warning when cut. Pages with almost no text stop the run before
   planning starts.
2. **Planning.** The material decides the number of episodes, unless the
   request sets it: one idea each, 450 to 700 spoken words. Every episode gets a
   summary, a scope, what it leaves to other episodes, the key facts, a common
   confusion, an example the sources give and a hook. Episodes build on each
   other. An independent check scores the title three times and replaces it if
   the median is below 8/10.
3. **Writing.** From the source text only, with numbers, names and dates kept
   exactly. Short sentences, one new term at a time, signposts, a hook first and
   the most useful takeaway last. No filler, nothing that only works on screen,
   names said the way people say them, and no invented people, stories or
   settings.
4. **Fact-check.** Every concrete claim (names, policies, roles, rules,
   deadlines, amounts, settings, dates, comparisons) is marked supported, not
   found or contradicted. Problems are fixed for up to two rounds.
5. **Listener review.** Every episode is scored from 1 to 10 on clarity, mental
   model, pacing, density, honesty, conciseness, coherence, and its opening and
   closing; the series is scored on flow. Episodes below 9 are rewritten and
   fact-checked again, for up to three rounds.

## The quality gate

A podcast is recorded only when the overall score is at least 8, the flow at
least 7, no episode below 6, and no claim is left unconfirmed. Otherwise the
transcripts are kept, the reasons are written to `podcast.json`, `create` exits
with `3`, and the audio generation UI says **Needs review**. A person can read the transcripts
and record it anyway.

## Audio checks

- **While recording:** a take outside 0.5 to 1.6 times the length at 140 words
  per minute is recorded again, up to three times.
- **After recording:** the take must be between 15% shorter and 30% longer than
  the text needs at 150 words per minute, and the first and last 30 seconds are
  transcribed: at least 70% of the first and last 25 words must be heard.
- **If a check fails,** the episode is recorded again in parts of four
  paragraphs. If it still fails, the run stops, no MP3 is kept, and you can
  re-record that episode on its own.
- **If the voice refuses the wording,** the script is rephrased in neutral words
  with every fact kept, recorded, and flagged for a person to read.

The checks are done by models. Review important podcasts before you publish
them, or use *Transcripts first*.
