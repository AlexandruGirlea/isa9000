from __future__ import annotations

import argparse
import sys

from isa9000.config import ConfigError, git_would_track, load_config, write_template
from isa9000.links import check_sources
from isa9000.podcast import cover_podcast, create_podcast, record_podcast
from isa9000.presentation_website import build_presentation_website, serve_presentation_website
from isa9000.progress import Progress, Step
from isa9000.version import __version__

DOCS = "https://alexandrugirlea.github.io/isa9000"
NEEDS_REVIEW = 3


def _reporter(args: argparse.Namespace) -> Progress:
    if args.progress == "json":
        return lambda step: print(step.to_json(), flush=True)
    return print


def _say(args: argparse.Namespace, text: str) -> None:
    if args.progress == "text":
        print(text)


def _init(args: argparse.Namespace) -> int:
    path = write_template(args.path, force=args.force)
    print(f"Wrote {path}. Add your Google credentials to it, then run: isa9000 audio-generation-ui")
    if git_would_track(path):
        print(f"Warning: git would commit {path}. It can hold credentials: add it to .gitignore.")
    return 0


def _check(args: argparse.Namespace) -> int:
    statuses = check_sources(args.sources)
    for status in statuses:
        mark = "ok" if status.ok else "!!"
        print(f"{mark}  {status.status:<15} {status.source}  {status.detail}")
    return 0 if all(status.ok for status in statuses) else 1


def _create(args: argparse.Namespace) -> int:
    result = create_podcast(
        args.request,
        args.sources,
        config=load_config(args.config),
        podcasts=args.audio_kb,
        audio=not args.text_only,
        progress=_reporter(args),
        follow_links=args.follow_links,
    )
    _say(args, f"\n{result.title}: {len(result.episodes)} episodes in {result.folder}")
    for episode in result.episodes:
        for problem in episode.unverified:
            _say(args, f"  check episode {episode.number}: {problem}")
    if not result.approved:
        print(
            f"isa9000: needs review before recording: {'; '.join(result.notes)}. Read the "
            f'transcripts, then record anyway with: isa9000 record "{result.folder}"',
            file=sys.stderr,
        )
        return NEEDS_REVIEW
    if args.text_only:
        _say(
            args, f'Review the transcripts, then record them with: isa9000 record "{result.folder}"'
        )
    return 0


def _record(args: argparse.Namespace) -> int:
    result = record_podcast(
        args.folder,
        load_config(args.config),
        progress=_reporter(args),
        force=args.force,
        episodes=set(args.episodes or []),
        chunked=args.chunked,
    )
    for episode in result.episodes:
        if episode.audio_note:
            _say(args, f"  listen to episode {episode.number}: {episode.audio_note}")
    return 0


def _cover(args: argparse.Namespace) -> int:
    cover_podcast(args.folder, load_config(args.config), progress=_reporter(args))
    return 0


def _presentation_website(args: argparse.Namespace) -> int:
    folder = build_presentation_website(
        load_config(args.config),
        podcasts=args.audio_kb,
        output=args.output,
        progress=_reporter(args),
    )
    if not args.serve:
        _say(args, f"Upload {folder} to your web server or storage: see {DOCS}/publishing.html")
        return 0
    serve_presentation_website(folder, args.port)
    return 0


def _audio_generation_ui(args: argparse.Namespace) -> int:
    from isa9000.audio_generation_ui.server import serve

    return serve(port=args.port, open_browser=not args.no_browser, config_path=args.config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="isa9000",
        description="AI-generated corporate podcasts from your documents and links.",
    )
    parser.add_argument("--version", action="version", version=f"isa9000 {__version__}")
    parser.add_argument(
        "--config",
        help="path to isa9000.toml (default: ./isa9000.toml, then ~/.config/isa9000/config.toml)",
    )
    parser.add_argument(
        "--progress",
        choices=("text", "json"),
        default="text",
        help="progress output: readable text, or one JSON object per line for other tools",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="write a starter isa9000.toml")
    init.add_argument("path", nargs="?", default="isa9000.toml")
    init.add_argument("--force", action="store_true", help="overwrite an existing file")
    init.set_defaults(run=_init)

    check = commands.add_parser("check", help="check that links, files and folders can be read")
    check.add_argument("sources", nargs="+")
    check.set_defaults(run=_check)

    library = "the audio knowledge base folder (default: [output] folder in the config)"
    create = commands.add_parser("create", help="create a podcast from a request and sources")
    create.add_argument("-r", "--request", required=True, help="what the podcast should cover")
    create.add_argument(
        "-s",
        "--source",
        dest="sources",
        action="append",
        required=True,
        help="link, file or folder; repeat for more",
    )
    create.add_argument("--audio-kb", help=library)
    create.add_argument(
        "--text-only",
        action="store_true",
        help="write transcripts only; record them later with 'isa9000 record'",
    )
    create.add_argument(
        "--follow-links",
        action="store_true",
        help="also read up to 25 pages linked from each web page, in the same section of its site",
    )
    create.set_defaults(run=_create)

    record = commands.add_parser("record", help="record audio for a podcast folder")
    record.add_argument("folder")
    record.add_argument("--force", action="store_true", help="record every episode again")
    record.add_argument(
        "-e",
        "--episode",
        dest="episodes",
        metavar="N",
        type=int,
        action="append",
        help="record only this episode again; repeat for more",
    )
    record.add_argument(
        "--chunked",
        action="store_true",
        help="record in parts of four paragraphs, for episodes that keep failing their check",
    )
    record.set_defaults(run=_record)

    cover = commands.add_parser("cover", help="draw new cover art for a podcast folder")
    cover.add_argument("folder")
    cover.set_defaults(run=_cover)

    presentation_website = commands.add_parser(
        "presentation-website",
        help="build the presentation website where people listen to your podcasts",
    )
    presentation_website.add_argument("--audio-kb", help=library)
    presentation_website.add_argument(
        "--output",
        help="the website folder (default: [presentation_website] folder in the config)",
    )
    presentation_website.add_argument(
        "--serve", action="store_true", help="preview the website after building it"
    )
    presentation_website.add_argument("--port", type=int, default=8800)
    presentation_website.set_defaults(run=_presentation_website)

    audio_generation_ui = commands.add_parser(
        "audio-generation-ui", help="open the audio generation UI in your browser"
    )
    audio_generation_ui.add_argument("--port", type=int, default=8790)
    audio_generation_ui.add_argument(
        "--no-browser", action="store_true", help="do not open a browser window"
    )
    audio_generation_ui.set_defaults(run=_audio_generation_ui)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        # Every failure reaches the user as one line, and its kind decides the exit code.
        if args.progress == "json":
            print(Step("error", str(error)).to_json(), flush=True)
        print(f"isa9000: {error}", file=sys.stderr)
        return 2 if isinstance(error, (ConfigError, ValueError)) else 1
