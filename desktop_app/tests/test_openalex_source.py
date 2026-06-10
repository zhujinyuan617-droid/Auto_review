"""Tests for OpenAlexSource — stateless, transport-injected authorship fetcher."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _fake_transport

from _fake_transport import FakeTransport

from autoreview_app.discovery.sources.openalex import OpenAlexSource, OPENALEX_WORKS_URL

DOI = "10.1016/j.fuel.2020.12345"
DOI_LOWER = "10.1016/j.fuel.2020.12345"  # already lower
CANNED_URL = OPENALEX_WORKS_URL.format(doi=DOI_LOWER)

CANNED_RESPONSE = {
    "authorships": [
        {
            "author": {"display_name": "Alice Wang"},
            "institutions": [
                {"display_name": "School of Petroleum Engineering, China University"}
            ],
        },
        {
            "author": {"display_name": "Bob Smith"},
            "institutions": [
                {"display_name": "MIT Energy Lab"},
                {"display_name": "School of Petroleum Engineering, China University"},  # same name, different author
            ],
        },
    ]
}


def _transport(doi=DOI_LOWER, response=CANNED_RESPONSE):
    url = OPENALEX_WORKS_URL.format(doi=doi)
    return FakeTransport(json_responses={url: response})


def test_fetch_authorship_maps_two_authors():
    transport = _transport()
    result = OpenAlexSource().fetch_authorship(DOI, transport)
    assert result is not None
    assert result["source"] == "openalex"
    authors = result["authors"]
    assert len(authors) == 2


def test_fetch_authorship_first_author_position_and_senior():
    transport = _transport()
    result = OpenAlexSource().fetch_authorship(DOI, transport)
    authors = result["authors"]
    assert authors[0]["name"] == "Alice Wang"
    assert authors[0]["position"] == 1
    assert authors[0]["is_senior"] is False


def test_fetch_authorship_last_author_is_senior():
    transport = _transport()
    result = OpenAlexSource().fetch_authorship(DOI, transport)
    authors = result["authors"]
    assert authors[1]["name"] == "Bob Smith"
    assert authors[1]["position"] == 2
    assert authors[1]["is_senior"] is True


def test_fetch_authorship_institutions_mapped():
    transport = _transport()
    result = OpenAlexSource().fetch_authorship(DOI, transport)
    authors = result["authors"]
    assert authors[0]["raw_affiliations"] == ["School of Petroleum Engineering, China University"]
    assert authors[1]["raw_affiliations"] == [
        "MIT Energy Lab",
        "School of Petroleum Engineering, China University",
    ]


def test_fetch_authorship_doi_lowercased_in_url():
    """URL must use lower-cased DOI regardless of input case."""
    upper_doi = "10.1016/J.FUEL.2020.12345"
    url_lower = OPENALEX_WORKS_URL.format(doi=upper_doi.lower())
    transport = FakeTransport(json_responses={url_lower: CANNED_RESPONSE})
    result = OpenAlexSource().fetch_authorship(upper_doi, transport)
    assert result is not None
    assert transport.json_calls[0][0] == url_lower


def test_fetch_authorship_records_url_called():
    transport = _transport()
    OpenAlexSource().fetch_authorship(DOI, transport)
    assert len(transport.json_calls) == 1
    called_url, params = transport.json_calls[0]
    assert called_url == CANNED_URL
    assert params == {}


def test_fetch_authorship_empty_authorships_returns_none():
    transport = _transport(response={"authorships": []})
    result = OpenAlexSource().fetch_authorship(DOI, transport)
    assert result is None


def test_fetch_authorship_missing_authorships_returns_none():
    transport = _transport(response={"id": "W123"})
    result = OpenAlexSource().fetch_authorship(DOI, transport)
    assert result is None


def test_fetch_authorship_skips_non_dict_items():
    response = {"authorships": ["bad", {"author": {"display_name": "Carol"}, "institutions": []}]}
    transport = _transport(response=response)
    result = OpenAlexSource().fetch_authorship(DOI, transport)
    assert result is not None
    # "bad" string is skipped; only Carol remains
    assert len(result["authors"]) == 1
    assert result["authors"][0]["name"] == "Carol"
