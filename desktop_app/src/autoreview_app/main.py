from __future__ import annotations

import threading

import uvicorn

from .api import create_app
from .config import AppConfig
from .server import HOST, build_window_url, find_free_port, wait_until_serving


def run_server(app, host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    config = AppConfig.from_env()
    app = create_app(config)
    port = find_free_port()

    thread = threading.Thread(
        target=run_server, args=(app, HOST, port), daemon=True
    )
    thread.start()

    if not wait_until_serving(HOST, port, timeout=15.0):
        raise RuntimeError(f"backend did not start on {HOST}:{port}")

    import webview  # local import so headless tests never load a GUI backend

    webview.create_window("Auto Review", build_window_url(HOST, port))
    webview.start()


if __name__ == "__main__":
    main()
