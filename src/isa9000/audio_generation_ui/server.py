from __future__ import annotations

import sys
import threading
import webbrowser


def serve(port: int = 8790, open_browser: bool = True, config_path: str | None = None) -> int:
    try:
        import uvicorn

        from isa9000.audio_generation_ui.app import create_app
    except ImportError:
        print(
            "the audio generation UI needs extras: pip install 'isa9000[audio-generation-ui]'",
            file=sys.stderr,
        )
        return 2

    url = f"http://127.0.0.1:{port}"
    config = uvicorn.Config(
        create_app(config_path), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    print(f"isa9000 on {url}  (ctrl-c to stop)")
    server.run()
    return 0 if server.started else 1
