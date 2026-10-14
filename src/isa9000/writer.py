from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from isa9000.sources import Source

LISTENER = """The listener is busy and listens on the go: they cannot look at a screen, pause \
to look something up or easily rewind. Many listeners are non-native English speakers. They \
are capable adults: do not over-explain, do not hand-hold, and do not use a motivational or \
hype tone. Keep the tone professional and respect their time."""

NO_INVENTION = """Never invent people, names, roles, organisations, places, events, dialogue, \
anecdotes or settings, and never place the listener or anyone else in an imagined situation \
such as an office, a meeting or a kitchen. Illustrate an idea only with an example the sources \
give, or a plain comparison that adds no facts; otherwise explain it directly."""

TITLE_MAX = 45
TITLE_RULES = f"""Podcast title: at most {TITLE_MAX} characters, read naturally when spoken \
(no emoji, slashes or hashtags). Lead with the name of the product, system, policy, team or \
event it is about: the words a colleague would search for. Say plainly what the listener \
gets. No filler words such as "Essentials", "Fundamentals", "Overview", "Deep Dive", \
"Introduction to", "Mastering" or "Platform", and no hype."""

COVER_RULE = """cover: a visual concept for the podcast cover art, at most 15 words: a background \
colour or mood and a single icon or symbol that represents the topic. Keep it minimal and \
flat-design friendly, for example "Soft purple background, single gear icon, clean modern feel"."""

TARGET_SCORE = 9
PASS_OVERALL = 8.0
PASS_FLOW = 7
PASS_EPISODE = 6
TITLE_PASS_SCORE = 8
TITLE_RUNS = 3


class EpisodePlan(BaseModel):
    title: str
    summary: str
    focus: str
    excludes: str
    key_points: list[str]
    misconception: str
    example: str
    hook: str
    sources: list[int]


class PodcastPlan(BaseModel):
    title: str
    description: str
    cover: str
    episodes: list[EpisodePlan]


class CoverIdea(BaseModel):
    cover: str


class Review(BaseModel):
    problems: list[str]


class EpisodeScore(BaseModel):
    episode_number: int
    score: int
    strengths: str
    issues: str
    suggestion: str


class PodcastScore(BaseModel):
    overall_score: float
    flow_score: int
    flow_issues: str
    flow_suggestion: str
    summary: str
    episodes: list[EpisodeScore]

    @property
    def approved(self) -> bool:
        lowest = min((episode.score for episode in self.episodes), default=0)
        return (
            self.overall_score >= PASS_OVERALL
            and self.flow_score >= PASS_FLOW
            and lowest >= PASS_EPISODE
        )


class TitleSuggestion(BaseModel):
    title: str
    score: int


class TitleScore(BaseModel):
    score: int
    reason: str
    suggestions: list[TitleSuggestion]


def _numbered(sources: list[Source], only: list[int] | None = None) -> str:
    wanted = {n for n in only or [] if 1 <= n <= len(sources)}
    blocks = [
        f"[{number}] {source.title}\n{source.ref}\n\n{source.text}"
        for number, source in enumerate(sources, start=1)
        if not wanted or number in wanted
    ]
    return "\n\n---\n\n".join(blocks)


def _text(client, model: str, prompt: str) -> str:
    text = client.text(model, prompt).strip()
    if not text:
        raise RuntimeError(f"{model} returned an empty script")
    return text


def plan_podcast(client, model: str, request: str, sources: list[Source]) -> PodcastPlan:
    prompt = f"""You plan short podcasts. A podcast is a short series of audio episodes. \
{LISTENER}

The listener asked for:
{request}

Plan a podcast that answers this request using only the numbered sources below. If the sources \
do not cover part of the request, leave that part out instead of guessing. {NO_INVENTION}

EPISODES
- If the request says how many episodes it wants, follow that exactly: it overrides every rule \
below about splitting or ordering episodes. Fit the scope to that number by covering the most \
important material and leaving out the rest.
- Otherwise, let the material decide the number of episodes. Each episode covers one focused \
idea that a writer can explain in 450 to 700 spoken words, about 3 to 5 minutes. Do not pad, \
and do not leave out anything the request asks for. A few excellent focused episodes are better \
than many thin ones.
- Do not create broad chapters. Group source passages that cover the same idea into one \
episode. Each episode owns its idea: before you finish, review the whole list and merge or trim \
episodes that would cover substantially the same ground.
- Feasibility check for every episode: can a writer explain this scope in about 600 words, \
including a hook, a walkthrough and one example? If not, narrow it, or split it when the \
request does not set the number of episodes. Warning signs: \
it draws on three or more unrelated sections; it covers both how something works internally \
and how to use it; it compares two things and explains one from scratch; its example needs \
ideas that have not been introduced yet.

ORDER
- The first one or two episodes establish what the subject is and why it matters to the \
listener.
- Each episode introduces at most one new abstraction and builds on the previous ones. Never \
rely on an idea before the episode that introduces it.
- Mind the density. After a heavy episode, follow with something more applied and concrete. \
Never put three demanding episodes in a row: the listener is listening, not reading.
- The final one or two episodes leave the listener with something practical they can act on.
- Treat the podcast as one arc with a clear direction.

FOR EACH EPISODE
- title: 2 to 6 plain words.
- summary: one or two plain sentences for the episode list, telling the listener what they \
will learn. Factual, no hype.
- focus: what this episode covers and the angle it takes.
- excludes: what it does NOT cover, because another episode owns it or the sources do not \
support it.
- key_points: the facts from the sources it must get across.
- misconception: what this is commonly confused with or mistaken for, if the sources make that \
clear; otherwise an empty string.
- example: one concrete example, case or situation that the sources themselves describe, with \
their specific details, or an empty string if they give none. Never reuse an example across \
episodes.
- hook: one sentence with a surprising fact, a common mistake or a practical tension from the \
sources that can open the episode.
- sources: the numbers of the sources it draws on.

{TITLE_RULES}
Description: two plain sentences on what the listener will know after the podcast.
{COVER_RULE}

Sources:
{_numbered(sources)}"""
    plan = client.structured(model, prompt, PodcastPlan)
    if not plan.episodes:
        raise RuntimeError("the plan has no episodes; the sources may not cover the request")
    return plan


def suggest_cover(client, model: str, title: str, description: str) -> str:
    prompt = f"""Suggest cover art for an internal podcast.
Title: {title}
Description: {description}

{COVER_RULE}"""
    return client.structured(model, prompt, CoverIdea).cover


def _score_title(client, model: str, plan: PodcastPlan) -> TitleScore:
    episodes = "\n".join(f"- {episode.title}: {episode.summary}" for episode in plan.episodes)
    prompt = f"""You name internal podcasts in a company's podcast library. The title is shown \
in the library, spoken at the start of every episode and used when colleagues search.

Score the podcast title below, then suggest better ones.

Criteria (1-10 each):
- findable: leads with the name of the product, system, policy, team or event, the words a \
colleague would search for. Generic or invented phrasing scores low.
- clear: says plainly what the listener gets. Filler words score low: "Essentials", \
"Fundamentals", "Overview", "Deep Dive", "Introduction to", "Mastering", "Platform".
- accurate: promises only what the episodes cover. Hype, ALL CAPS or claims the content does \
not support score low.

Hard limits: at most {TITLE_MAX} characters; reads naturally when spoken (no emoji, no slashes, \
no hashtags). A title over {TITLE_MAX} characters cannot score above 5 overall.

"score" is your overall judgment. 8 or more means ready to publish. Suggest exactly 3 \
alternative titles, best first, each within the hard limits, accurate to the episodes, and \
scored the same way.

Title: {plan.title}
Description: {plan.description}
Episodes:
{episodes}"""
    return client.structured(model, prompt, TitleScore)


def review_title(client, model: str, plan: PodcastPlan) -> tuple[str, int]:
    with ThreadPoolExecutor(max_workers=TITLE_RUNS) as pool:
        runs = list(pool.map(lambda _: _score_title(client, model, plan), range(TITLE_RUNS)))
    score = int(statistics.median(run.score for run in runs))
    if score >= TITLE_PASS_SCORE:
        return plan.title, score
    options = [
        option
        for run in runs
        for option in run.suggestions
        if 0 < len(option.title.strip()) <= TITLE_MAX
    ]
    best = max(options, key=lambda option: option.score, default=None)
    if best is None or best.score <= score:
        return plan.title, score
    return best.title.strip(), best.score


def _outline(plan: PodcastPlan) -> str:
    return "\n".join(
        f"{number}. {item.title}: {item.focus}"
        for number, item in enumerate(plan.episodes, start=1)
    )


def write_episode(
    client,
    model: str,
    plan: PodcastPlan,
    index: int,
    sources: list[Source],
    current: str | None = None,
    notes: list[str] | None = None,
) -> str:
    episode = plan.episodes[index]
    points = "\n".join(f"- {point}" for point in episode.key_points)
    revision = ""
    if current:
        listed = "\n".join(f"- {note}" for note in notes or [])
        revision = f"""REVISION
Below is the current script. Rewrite it to fix every issue listed. Keep what already works, \
keep following every rule above, and keep every fact grounded in the sources.
Issues to fix:
{listed}

Current script:
{current}

"""
    prompt = f"""You write one episode of a podcast. {LISTENER} The listener should take away \
one clear idea from this episode and leave knowing something concrete they can use.

Podcast: {plan.title}
Outline:
{_outline(plan)}

Write the script for episode {index + 1} of {len(plan.episodes)}: {episode.title}
Focus: {episode.focus}
Does not cover: {episode.excludes}
Key points:
{points}
Common confusion: {episode.misconception or "none given"}
Example from the sources: {episode.example or "none given"}
Hook idea: {episode.hook}

RULES
1. STAY ON POINT: this episode is only about "{episode.title}". Do not explain related ideas or \
broader context. If you need another idea, mention it by name only: it has its own episode.
2. SOURCES ONLY: base every claim, number, name, date and example on the sources below. If \
something is not in the sources, leave it out; when in doubt, leave it out. {NO_INVENTION} \
Keep every number, name and date exactly as the sources state it. If a common confusion is \
given, clear it up in one short sentence: say what it is not, then what it is.
3. NO FLUFF: get to the substance fast. Every sentence must inform or connect two ideas. Banned \
phrases: "Imagine a world", "In today's fast-paced", "It's worth noting", "It's important to \
understand", "Let's dive in", "As you might already know", "Without further ado", "So, what \
is", "Let's break it down", "You might be wondering", and any variation. Do not repeat or \
summarize what you just said: say it once, clearly, and move on.
4. GLOBAL ENGLISH: simple, everyday words for everything that is not a technical or business \
term. Short sentences. Active voice. No idioms, no slang, no culturally specific references. \
Use the correct terms for the subject itself; never water them down.
5. VOICE AND RHYTHM: this script is read aloud. Write the way a knowledgeable professional \
explains something out loud: direct, calm, a little dry. Not a lecture, not a sales pitch. Vary \
sentence length: follow a longer explanation with a short, direct line. Introduce only one new \
term at a time: say it, use it in a short sentence, then move on. Never put two unfamiliar \
terms in the same sentence. When the episode covers several points in sequence, help the \
listener keep track with verbal numbering or short bridges ("Now, the second part of this..."). \
When density is high you may use one natural, context-specific sentence to refocus attention, \
never a stock phrase; most episodes need none.
6. STRUCTURE (a guide, not a template): open with one or two sentences that create curiosity: \
a concrete problem, a surprising fact, a common mistake or a tension the listener recognises, \
taken from the sources. Then name the topic as the answer. If the reason it matters is not \
obvious, explain the problem it solves; in the first episodes, always do. Walk through how it \
works, step by step. Make abstract ideas tangible with the example and the specific details \
the sources give.
7. CLOSING THOUGHT: the last sentence must be the single most useful takeaway of the episode. \
Not a summary, not a procedural detail, not generic encouragement. Do not add a greeting, a \
sign-off or a teaser for other episodes: the intro and outro are added separately.
8. LENGTH: between 450 and 700 words. If you run long, cut examples, not explanations.
9. NOTHING THAT ONLY WORKS ON SCREEN: no markdown, bullet points, numbered lists, headings, \
tables, URLs, file paths, code or speaker tags. Explain procedures, calculations and any code \
as a plain spoken walkthrough. Do not read out menu paths, click-by-click steps or long lists of \
settings, permissions or tiers. Write continuous paragraphs.
10. SAY NAMES THE WAY PEOPLE SAY THEM: write acronyms and product names as people normally say \
them. Never spell them letter by letter with spaces, and never expand product or model names. \
Expand an abbreviation once only if listeners are unlikely to know it.

{revision}Sources:
{_numbered(sources, episode.sources)}"""
    return _text(client, model, prompt)


def rephrase_for_voice(client, model: str, script: str) -> str:
    prompt = f"""The text-to-speech service refused to read the script below because of its \
safety filters. Rewrite it so it can be read aloud: use neutral, factual wording, and avoid \
graphic descriptions, references to dangerous substances, or anything else that could be \
flagged as harmful or sensitive.

Keep every fact, number, name and date exactly as it is. Keep the first and the last paragraph \
word for word. Keep the same structure and about the same length. Return only the script.

Script:
{script}"""
    return _text(client, model, prompt)


def review_episode(
    client, model: str, script: str, sources: list[Source], episode: EpisodePlan
) -> list[str]:
    prompt = f"""You are a strict fact-checker for a podcast episode. Compare the script with \
the sources.

List every concrete claim in the script: names of policies, products, systems, teams, roles, \
people and features; rules, eligibility, responsibilities and deadlines; settings and defaults; \
limits, amounts, prices and percentages; numbers, versions and dates; behaviours and \
comparisons. Check each one against the sources: SUPPORTED, NOT FOUND or CONTRADICTED.

Report as a problem, each with a short correction based on the sources:
- every CONTRADICTED claim;
- every NOT FOUND claim that states a specific fact;
- invented numbers: amounts, prices, targets, results, benchmarks, adoption figures, dates;
- invented or misnamed policies, products, features, settings, teams, people or companies;
- invented people, characters, roles, organisations, places, events, anecdotes or situations, \
including hypothetical ones the sources do not describe;
- wrong versions, or features presented as available that the sources do not describe as \
available;
- security, legal, financial or medical guidance that is wrong or risky.

Do not report SUPPORTED claims. Ignore style, tone and wording. If there are no problems, \
return an empty list.

Script:
{script}

Sources:
{_numbered(sources, episode.sources)}"""
    return client.structured(model, prompt, Review).problems


def score_podcast(client, model: str, plan: PodcastPlan, scripts: list[str]) -> PodcastScore:
    episodes = "\n\n".join(
        f"=== Episode {number}: {item.title} ===\n{script}"
        for number, (item, script) in enumerate(zip(plan.episodes, scripts, strict=True), start=1)
    )
    prompt = f"""You are an expert podcast quality evaluator.

You are scoring a {len(scripts)}-episode podcast titled "{plan.title}". These episodes are \
AUDIO-ONLY: no visuals, no slides, no screen. The listener is busy and multitasking, often on \
the move. They are distracted. They cannot pause to look things up. They cannot rewind easily. \
Each episode is 3 to 5 minutes. A fixed spoken \
greeting and sign-off are added to every episode separately, so they are not in the scripts.

OBJECTIVITY RULES:
- You are an independent evaluator. You did NOT write these scripts. You have no stake in them \
passing or failing. Score what you hear, not what you hope.
- Do NOT inflate scores out of politeness or because the topic is interesting. A dull topic \
with a great script beats an exciting topic with a mediocre one.
- If an episode genuinely deserves a 9 or 10, give it. But if you find yourself giving high \
scores across the board, pause and re-read: are you being rigorous or generous? Most episodes \
have at least one weakness.
- Base every score on specific evidence from the script. "Good engagement" is not a \
justification; "opens with a concrete problem and uses one example from the sources to explain \
the idea" is.
- A 7 is not a bad score. It means "solid, room for improvement." Reserve 9-10 for episodes \
that genuinely surprise you with their quality.
- Our production target is 9+. Be honest about what meets that bar and what does not.

SCORING CRITERIA (evaluate each episode on ALL 8):
1. AUDIO CLARITY: Can the listener follow purely by ear? References to "see below", "as \
shown", code, diagrams, tables, URLs or symbols are critical failures in audio. Are sentences \
short enough to follow at normal playback speed? Long sentences with several clauses or stacked \
jargon lose distracted listeners.
2. MENTAL MODEL: the most important criterion. The script must paint pictures with words so \
the listener builds a mental model: concrete examples from the sources, plain comparisons, what \
something does and looks like in practice, not only what it is. Jargon walls and bare acronym \
lists are bad. Test: with closed eyes, could the listener sketch what was just explained?
3. ENGAGEMENT AND PACING: Does it open with a hook (a surprising fact, a real problem, a \
common mistake)? Is the pace right for someone who cannot rewind? Does it avoid \
monotonous listing? Are transitions smooth and signposted?
4. INFORMATION DENSITY: substantive enough for capable professionals, without cramming too \
much into one episode. Respects the listener's intelligence without being impenetrable.
5. HONESTY AND TRUST: no over-promising ("you'll master X"), no marketing language, hype or \
empty superlatives. Invented people, stories or situations are a critical failure. Would an \
expert respect it?
6. CONCISENESS: every sentence earns its place. No filler, repetition, padding or \
throat-clearing ("In this episode we're going to look at...").
7. STANDALONE COHERENCE: Does the episode make sense on its own? Are key terms explained when \
first introduced?
8. OPENING AND CLOSING: Does the script open with a hook before naming the topic? Is the last \
sentence the single most useful takeaway, rather than a summary or generic encouragement? Does \
the final episode avoid promising future episodes or podcasts?
9. PODCAST FLOW (evaluated once for the whole podcast): logical progression where each episode \
builds on the previous one; no awkward jumps; no idea used before it is introduced; no \
repetition between episodes, and no example reused; consistent terminology; an arc \
that opens with a clear foundation and closes with something practical.

SCORING SCALE (episode and flow scores):
- 9-10: Excellent: ready to publish, engaging, clear and tight
- 7-8: Good: minor issues, publishable but could improve
- 5-6: Needs work: noticeable problems that would frustrate listeners
- 3-4: Significant issues: confusing, too visual or poorly structured
- 1-2: Major rewrite needed: fundamentally broken for audio

Return overall_score (the average of the episode scores), flow_score (1-10), flow_issues and \
flow_suggestion (1-2 sentences each, or "None" if flow_score is 9 or more), summary (2-3 \
sentences including flow), and for every episode: episode_number, score (1-10), strengths (one \
sentence with specific evidence), issues (one sentence with specific evidence, or "None" if \
the score is 9 or more) and suggestion (one sentence with a specific fix, or "None" if the score \
is 9 or more).

{episodes}"""
    return client.structured(model, prompt, PodcastScore)
