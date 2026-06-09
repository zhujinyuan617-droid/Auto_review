from __future__ import annotations

import dataclasses
import threading
from pathlib import Path

import uvicorn

from .api import create_app
from .config import AppConfig
from .server import HOST, build_window_url, find_free_port, wait_until_serving


def with_connection_paths(config: AppConfig, connection_dir: Path) -> AppConfig:
    """Point the config at the engine's connection artifacts when they exist.

    The connection layer's edges.json / concept_index.json live in the engine's
    reports dir, not beside the library. Wiring them here lets the network and
    writing-angles screens show real data without changing the engine.
    """
    edges = connection_dir / "edges.json"
    cidx = connection_dir / "concept_index.json"
    return dataclasses.replace(
        config,
        edges_path=edges if edges.is_file() else config.edges_path,
        concept_index_path=cidx if cidx.is_file() else config.concept_index_path,
    )


def run_server(app, host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    connection_dir = Path(__file__).resolve().parents[3] / "Document_Decomposer" / "reports" / "connection"
    config = with_connection_paths(AppConfig.from_env(), connection_dir)
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
