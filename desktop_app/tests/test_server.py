import socket

from autoreview_app.server import (
    HOST,
    build_window_url,
    find_free_port,
    wait_until_serving,
)


def test_host_is_loopback():
    assert HOST == "127.0.0.1"


def test_find_free_port_in_valid_range():
    # find_free_port already bound the port internally to obtain it, so the
    # bindability is exercised there. Re-binding here would add a TOCTOU race
    # (the port could be taken between calls) for no extra coverage; just check
    # we got a plausible port number.
    port = find_free_port()
    assert isinstance(port, int)
    assert 1 <= port <= 65535


def test_build_window_url():
    assert build_window_url(HOST, 8123) == "http://127.0.0.1:8123/"


def test_wait_until_serving_true_when_listening():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((HOST, 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        assert wait_until_serving(HOST, port, timeout=2.0) is True


def test_wait_until_serving_false_on_timeout():
    # find_free_port gives a port nobody is listening on.
    port = find_free_port()
    assert wait_until_serving(HOST, port, timeout=0.5) is False
