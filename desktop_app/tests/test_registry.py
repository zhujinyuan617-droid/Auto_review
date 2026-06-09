from autoreview_app.discovery.records import CitationRecord
from autoreview_app.discovery.registry import SourceRegistry


class _Searchable:
    name = "searchy"
    can_search = True
    can_fetch = False

    def search(self, query, transport, rows=20):
        return [CitationRecord(title=f"hit:{query}")]

    def fetch(self, record, transport):
        return None


class _Fetchable:
    name = "fetchy"
    can_search = False
    can_fetch = True

    def search(self, query, transport, rows=20):
        return []

    def fetch(self, record, transport):
        return b"%PDF-1.4"


def test_register_and_list():
    reg = SourceRegistry()
    reg.register(_Searchable())
    reg.register(_Fetchable())
    assert {s.name for s in reg.all()} == {"searchy", "fetchy"}


def test_searchable_and_fetchable_filters():
    reg = SourceRegistry()
    reg.register(_Searchable())
    reg.register(_Fetchable())
    assert [s.name for s in reg.searchable()] == ["searchy"]
    assert [s.name for s in reg.fetchable()] == ["fetchy"]


def test_get_by_name():
    reg = SourceRegistry()
    s = _Searchable()
    reg.register(s)
    assert reg.get("searchy") is s
    assert reg.get("missing") is None
