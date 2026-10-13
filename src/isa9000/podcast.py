from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from isa9000.art import draw_cover
from isa9000.config import GIT_IGNORE_ALL, Config, genai_client, load_config, render
from isa9000.links import SourceStatus, check_sources
from isa9000.progress import Progress, Step
from isa9000.sources import Source, load_sources, thin_pages
from isa9000.version import __version__
from isa9000.voice import Speaker, VoiceRefused, record_episode
from isa9000.writer import (
    PASS_EPISODE,
    PASS_FLOW,
    PASS_OVERALL,
    TARGET_SCORE,
    PodcastPlan,
    PodcastScore,
    plan_podcast,
    rephrase_for_voice,
    review_episode,
    review_title,
    score_podcast,
    suggest_cover,
    write_episode,
)

MANIFEST = "podcast.json"
WORKERS = 5
FACT_CHECK_ROUNDS = 2
REVIEW_ROUNDS = 3


class SourceError(RuntimeError):
    def __init__(self, statuses: list[SourceStatus]) -> None:
        self.statuses = statuses
        lines = "\n".join(f"  {s.status}: {s.source} ({s.detail})" for s in statuses)
        super().__init__(f"fix these sources first:\n{lines}")


@dataclass
class EpisodeResult:
    number: int
    title: str
    transcript: Path
    audio: Path | None = None
    seconds: float | None = None
    unverified: list[str] = field(default_factory=list)
    audio_note: str = ""


@dataclass
class PodcastResult:
    title: str
    description: str
    folder: Path
    episodes: list[EpisodeResult]
    approved: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class _Drafting:
    client: object
    model: str
    plan: PodcastPlan
    sources: list[Source]
    fact_check: bool
    progress: Progress


def safe_name(text: str, limit: int = 80) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned[:limit].rstrip() or "untitled"


def member(folder: Path, name: str) -> Path:
    # Anyone who can edit the library can edit podcast.json, so it may only name files that sit
    # directly in its own folder.
    if not name or Path(name).name != name or name.startswith("."):
        raise ValueError(f"{folder / MANIFEST} names a file outside its folder: {name!r}")
    return folder / name


def load_manifest(folder: Path) -> dict:
    return json.loads((folder / MANIFEST).read_text(encoding="utf-8"))


def _save(folder: Path, manifest: dict) -> None:
    draft = folder / f".{MANIFEST}.tmp"
    draft.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(draft, folder / MANIFEST)


def _new_folder(root: Path, title: str) -> Path:
    if not root.exists():
        root.mkdir(parents=True)
        (root / ".gitignore").write_text(GIT_IGNORE_ALL)
    base = root / f"{date.today().isoformat()} - {safe_name(title)}"
    folder, copy = base, 2
    while folder.exists():
        folder = base.with_name(f"{base.name} ({copy})")
        copy += 1
    folder.mkdir(parents=True)
    return folder


def _spoken(config: Config, plan: PodcastPlan, number: int, body: str) -> str:
    total = len(plan.episodes)
    values = {
        "narrator": config.narrator.name,
        "brand": config.branding.brand,
        "podcast": plan.title,
        "episode": number,
        "episodes": total,
        "title": plan.episodes[number - 1].title,
        "powered_by": config.branding.powered_by,
    }
    closing = config.branding.final_ending if number == total else config.branding.ending
    parts = (render(config.branding.greeting, **values), body.strip(), render(closing, **values))
    return "\n\n".join(part for part in parts if part) + "\n"


def _result(folder: Path, manifest: dict) -> PodcastResult:
    episodes = [
        EpisodeResult(
            number=entry["number"],
            title=entry["title"],
            transcript=member(folder, entry["transcript"]),
            audio=member(folder, entry["audio"]) if entry.get("audio") else None,
            seconds=entry.get("seconds"),
            unverified=entry.get("unverified", []),
            audio_note=entry.get("audio_note", ""),
        )
        for entry in manifest["episodes"]
    ]
    review = manifest.get("review", {})
    return PodcastResult(
        manifest["title"],
        manifest.get("description", ""),
        folder,
        episodes,
        approved=review.get("approved", True),
        notes=review.get("notes", []),
    )


def _read(
    sources: list[str], client, model: str, progress: Progress, follow_links: bool
) -> list[Source]:
    progress(Step("read", "Reading the sources"))
    loaded = load_sources(sources, client, model, progress, follow_links)
    if not loaded:
        raise RuntimeError("no readable text was found in the sources")
    thin = thin_pages(loaded)
    if thin:
        detail = (
            "the page may need JavaScript or a sign-in; use an exported copy or a synced folder"
        )
        raise SourceError(
            [
                SourceStatus(s.ref, False, "too_little_text", f"{len(s.text)} characters: {detail}")
                for s in thin
            ]
        )
    return loaded


def _fact_checked(work: _Drafting, index: int, body: str) -> tuple[str, list[str]]:
    if not work.fact_check:
        return body, []
    number, total = index + 1, len(work.plan.episodes)
    episode = work.plan.episodes[index]
    work.progress(Step("verify", f"Fact-checking episode {number}/{total}", number, total))
    problems = review_episode(work.client, work.model, body, work.sources, episode)
    for _ in range(FACT_CHECK_ROUNDS):
        if not problems:
            break
        work.progress(
            Step(
                "verify",
                f"Fixing {len(problems)} fact(s) in episode {number}/{total}",
                number,
                total,
            )
        )
        body = write_episode(
            work.client, work.model, work.plan, index, work.sources, current=body, notes=problems
        )
        problems = review_episode(work.client, work.model, body, work.sources, episode)
    return body, problems


def _draft(work: _Drafting, index: int) -> tuple[str, list[str]]:
    number, total = index + 1, len(work.plan.episodes)
    work.progress(
        Step(
            "write",
            f"Writing episode {number}/{total}: {work.plan.episodes[index].title}",
            number,
            total,
        )
    )
    body = write_episode(work.client, work.model, work.plan, index, work.sources)
    return _fact_checked(work, index, body)


def _polish(work: _Drafting, bodies: list[str], unverified: list[list[str]]) -> PodcastScore:
    total = len(work.plan.episodes)
    work.progress(Step("review", "Reviewing the episodes as a listener would"))
    score = score_podcast(work.client, work.model, work.plan, bodies)
    for round_number in range(1, REVIEW_ROUNDS + 1):
        weak = [
            item
            for item in score.episodes
            if item.score < TARGET_SCORE and 1 <= item.episode_number <= total
        ]
        if not weak:
            break
        work.progress(
            Step(
                "review",
                f"Polishing {len(weak)} episode(s), round {round_number} of {REVIEW_ROUNDS}",
            )
        )

        def rewrite(item) -> tuple[int, str, list[str]]:
            index = item.episode_number - 1
            notes = [
                f"{label}: {text}"
                for label, text in (("Problem", item.issues), ("Fix", item.suggestion))
                if text and text.strip() != "None"
            ]
            body = write_episode(
                work.client,
                work.model,
                work.plan,
                index,
                work.sources,
                current=bodies[index],
                notes=notes,
            )
            return (index, *_fact_checked(work, index, body))

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for index, body, problems in pool.map(rewrite, weak):
                bodies[index], unverified[index] = body, problems
        work.progress(Step("review", "Reviewing the episodes again"))
        score = score_podcast(work.client, work.model, work.plan, bodies)
    return score


def _review_notes(score: PodcastScore, unverified: list[list[str]]) -> list[str]:
    notes = []
    if not score.approved:
        lowest = min((item.score for item in score.episodes), default=0)
        notes.append(
            f"quality {score.overall_score:.1f}/10, flow {score.flow_score}/10, lowest episode "
            f"{lowest}/10 (needs {PASS_OVERALL:g}, {PASS_FLOW} and {PASS_EPISODE})"
        )
    notes += [
        f"episode {number} has {len(problems)} unconfirmed claim(s)"
        for number, problems in enumerate(unverified, start=1)
        if problems
    ]
    return notes


def _cover(
    client, config: Config, plan: PodcastPlan, folder: Path, progress: Progress
) -> str | None:
    try:
        return draw_cover(
            client, config.models.image, plan.title, plan.cover, config.branding.brand, folder
        )
    except Exception as error:
        # The paid-for episodes matter more than the cover, which can be drawn again later.
        progress(
            Step("write", f"Could not draw the cover ({error}); draw it later with: isa9000 cover")
        )
        return None


def _episodes(
    config: Config,
    plan: PodcastPlan,
    folder: Path,
    bodies: list[str],
    score: PodcastScore,
    unverified: list[list[str]],
) -> list[dict]:
    scores = {item.episode_number: item for item in score.episodes}
    entries = []
    for index, episode in enumerate(plan.episodes):
        number = index + 1
        transcript = folder / f"{number:02d} - {safe_name(episode.title)}.txt"
        transcript.write_text(_spoken(config, plan, number, bodies[index]), encoding="utf-8")
        rated = scores.get(number)
        entries.append(
            {
                "number": number,
                "title": episode.title,
                "summary": episode.summary,
                "transcript": transcript.name,
                "audio": None,
                "seconds": None,
                "score": rated.score if rated else None,
                "issues": rated.issues if rated else "",
                "unverified": unverified[index],
            }
        )
    return entries


def create_podcast(
    request: str,
    sources: list[str],
    config: Config | None = None,
    podcasts: str | Path | None = None,
    audio: bool = True,
    progress: Progress = print,
    follow_links: bool = False,
) -> PodcastResult:
    config = config or load_config()
    if not request.strip():
        raise ValueError("describe what the podcast should cover")
    if not sources:
        raise ValueError("add at least one link, file or folder")

    progress(Step("check", f"Checking {len(sources)} source(s)"))
    failed = [status for status in check_sources(sources) if not status.ok]
    if failed:
        raise SourceError(failed)
    client = genai_client(config)
    model = config.models.text
    loaded = _read(sources, client, model, progress, follow_links)

    progress(Step("plan", f"Planning the podcast from {len(loaded)} document(s)"))
    plan = plan_podcast(client, model, request, loaded)
    plan.title, title_score = review_title(client, model, plan)
    folder = _new_folder(
        Path(podcasts).expanduser() if podcasts else config.output_folder, plan.title
    )
    total = len(plan.episodes)
    progress(
        Step("plan", f"Podcast: {plan.title} ({total} episodes)", total=total, folder=str(folder))
    )

    work = _Drafting(client, model, plan, loaded, config.output.fact_check, progress)
    with ThreadPoolExecutor(max_workers=1) as artist:
        progress(Step("write", "Drawing the cover art"))
        cover = artist.submit(_cover, client, config, plan, folder, progress)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            drafts = list(pool.map(lambda index: _draft(work, index), range(total)))
    bodies = [body for body, _ in drafts]
    unverified = [problems for _, problems in drafts]
    score = _polish(work, bodies, unverified)
    notes = _review_notes(score, unverified)

    manifest = {
        "title": plan.title,
        "description": plan.description,
        "request": request,
        "sources": sources,
        "read": [source.ref for source in loaded],
        "cover": cover.result(),
        "cover_concept": plan.cover,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "narrator": config.narrator.name,
        "models": {"text": config.models.text, "speech": config.models.speech},
        "generator": f"isa9000 {__version__}",
        "powered_by": config.branding.powered_by,
        "review": {
            "approved": not notes,
            "notes": notes,
            "fact_checked": config.output.fact_check,
            "score": score.overall_score,
            "flow": score.flow_score,
            "flow_issues": score.flow_issues,
            "summary": score.summary,
            "title_score": title_score,
        },
        "episodes": _episodes(config, plan, folder, bodies, score, unverified),
    }
    _save(folder, manifest)
    if notes:
        progress(Step("review", f"Needs review before recording: {'; '.join(notes)}"))
        return _result(folder, manifest)
    if not audio:
        progress(Step("done", f"Transcripts ready in {folder}", folder=str(folder)))
        return _result(folder, manifest)
    return record_podcast(folder, config, progress=progress)


def cover_podcast(
    folder: str | Path, config: Config | None = None, progress: Progress = print
) -> Path:
    config = config or load_config()
    folder = Path(folder).expanduser()
    manifest = load_manifest(folder)
    client = genai_client(config)
    concept = manifest.get("cover_concept") or suggest_cover(
        client, config.models.text, manifest["title"], manifest.get("description", "")
    )
    progress(Step("write", f"Drawing the cover art: {concept}"))
    name = draw_cover(
        client, config.models.image, manifest["title"], concept, config.branding.brand, folder
    )
    manifest["cover"], manifest["cover_concept"] = name, concept
    _save(folder, manifest)
    progress(Step("done", f"Cover saved as {folder / name}", folder=str(folder)))
    return folder / name


def record_podcast(
    folder: str | Path,
    config: Config | None = None,
    progress: Progress = print,
    force: bool = False,
    episodes: set[int] | None = None,
    chunked: bool = False,
) -> PodcastResult:
    config = config or load_config()
    folder = Path(folder).expanduser()
    manifest = load_manifest(folder)
    total = len(manifest["episodes"])
    unknown = sorted((episodes or set()) - {entry["number"] for entry in manifest["episodes"]})
    if unknown:
        raise ValueError(
            f"no episode {', '.join(map(str, unknown))} in {folder.name} (it has {total})"
        )
    if episodes:
        pending = [entry for entry in manifest["episodes"] if entry["number"] in episodes]
    else:
        pending = [
            entry
            for entry in manifest["episodes"]
            if force or not member(folder, entry["transcript"]).with_suffix(".mp3").exists()
        ]
    speaker = Speaker(
        genai_client(config),
        config.models.speech,
        config.narrator.voice,
        config.narrator.style,
        config.models.text,
        config.narrator.pronunciations,
    )
    lock = threading.Lock()

    def record(entry: dict) -> None:
        number = entry["number"]
        transcript = member(folder, entry["transcript"])
        mp3 = transcript.with_suffix(".mp3")
        progress(
            Step("record", f"Recording episode {number}/{total}: {entry['title']}", number, total)
        )

        def retry(problems: list[str]) -> None:
            message = (
                f"Recording episode {number}/{total} again in shorter parts: {'; '.join(problems)}"
            )
            progress(Step("record", message, number, total))

        text = transcript.read_text(encoding="utf-8")
        note = entry.get("audio_note", "")
        try:
            seconds = record_episode(speaker, text, mp3, retry, chunked)
        except VoiceRefused:
            progress(
                Step(
                    "record",
                    f"The voice refused episode {number}/{total}; rephrasing it",
                    number,
                    total,
                )
            )
            text = rephrase_for_voice(speaker.client, config.models.text, text).rstrip() + "\n"
            transcript.write_text(text, encoding="utf-8")
            seconds = record_episode(speaker, text, mp3, retry, chunked)
            note = (
                "the voice refused the original wording, so the script was rephrased: "
                "read the new transcript"
            )
        with lock:
            entry["audio"] = mp3.name
            entry["seconds"] = round(seconds, 1)
            entry["audio_note"] = note
            manifest["voice"] = config.narrator.voice
            _save(folder, manifest)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(record, pending))
    progress(Step("done", f"Podcast ready in {folder}", folder=str(folder)))
    return _result(folder, manifest)
