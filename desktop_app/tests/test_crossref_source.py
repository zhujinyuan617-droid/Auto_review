from _fake_transport import FakeTransport

from autoreview_app.discovery.sources.crossref import CrossrefSource

CROSSREF_URL = "https://api.crossref.org/works"

CANNED = {
    "message": {
        "items": [
            {
                "DOI": "10.1016/j.fuel.2020.12345",
                "title": ["A Study of Methane Adsorption"],
                "container-title": ["Fuel"],
                "published": {"date-parts": [[2020, 5]]},
                "author": [{"family": "Smith", "given": "John"}],
            },
            {
                "DOI": "10.1000/xyz",
                "title": ["Untitled Dataset"],
                "container-title": [],
                "issued": {"date-parts": [[2018]]},
                "author": [],
            },
        ]
    }
}


def test_capabilities():
    src = CrossrefSource()
    assert src.name == "crossref"
    assert src.can_search is True
    assert src.can_fetch is False


def test_search_maps_items_to_records():
    transport = FakeTransport(json_responses={CROSSREF_URL: CANNED})
    records = CrossrefSource().search("methane", transport, rows=2)

    assert transport.json_calls[0][0] == CROSSREF_URL
    assert transport.json_calls[0][1]["query"] == "methane"
    assert transport.json_calls[0][1]["rows"] == "2"

    assert records[0].doi == "10.1016/j.fuel.2020.12345"
    assert records[0].title == "A Study of Methane Adsorption"
    assert records[0].journal == "Fuel"
    assert records[0].year == "2020"
    assert records[0].authors == ("Smith, John",)
    assert records[1].year == "2018"
    assert records[1].journal == ""


def test_fetch_by_doi_maps_message_to_record():
    doi = "10.1063/1.2764109"
    url = CROSSREF_URL + "/" + doi
    canned = {"message": {
        "DOI": doi, "title": ["Hindered settling"], "container-title": ["PoF"],
        "issued": {"date-parts": [[2007]]},
        "author": [{"family": "Yin", "given": "Xiaolong"}, {"family": "Koch", "given": "Donald L."}],
    }}
    transport = FakeTransport(json_responses={url: canned})
    rec = CrossrefSource().fetch_by_doi(doi, transport)
    assert rec is not None
    assert rec.doi == doi
    assert rec.authors == ("Yin, Xiaolong", "Koch, Donald L.")


def test_fetch_by_doi_none_when_no_message():
    url = CROSSREF_URL + "/10.0/missing"
    transport = FakeTransport(json_responses={url: {"status": "ok"}})
    assert CrossrefSource().fetch_by_doi("10.0/missing", transport) is None
