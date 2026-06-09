from __future__ import annotations

import socket
import time

HOST = "127.0.0.1"


def find_free_port() -> int:
    """Ask the OS for a free TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def build_window_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/"


def wait_until_serving(host: str, port: int, timeout: float = 10.0) -> bool:
    """Poll until something accepts TCP connections at host:port, or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False
