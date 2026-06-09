from _fake_transport import FakeTransport


def test_fake_transport_returns_canned_json():
    t = FakeTransport(json_responses={"http://x/api": {"ok": True}})
    assert t.get_json("http://x/api", params={}) == {"ok": True}


def test_fake_transport_returns_canned_bytes():
    t = FakeTransport(byte_responses={"http://x/f.pdf": b"%PDF-1.4 data"})
    assert t.get_bytes("http://x/f.pdf") == b"%PDF-1.4 data"


def test_fake_transport_missing_url_raises():
    t = FakeTransport()
    try:
        t.get_bytes("http://missing")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unmapped url")
