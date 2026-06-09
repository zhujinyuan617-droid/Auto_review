from autoreview_app.discovery.ris import parse_ris_text

SAMPLE = """TY  - JOUR
TI  - A Study of Methane Adsorption
AU  - Smith, John
AU  - Doe, Jane
T2  - Fuel
PY  - 2020
DO  - 10.1016/j.fuel.2020.12345
ER  -

TY  - JOUR
TI  - Second Paper
PY  - 2019
ER  -
"""


def test_parses_two_records():
    records = parse_ris_text(SAMPLE)
    assert len(records) == 2


def test_first_record_fields():
    rec = parse_ris_text(SAMPLE)[0]
    assert rec.title == "A Study of Methane Adsorption"
    assert rec.authors == ("Smith, John", "Doe, Jane")
    assert rec.journal == "Fuel"
    assert rec.year == "2020"
    assert rec.doi == "10.1016/j.fuel.2020.12345"


def test_record_without_doi_has_empty_doi():
    rec = parse_ris_text(SAMPLE)[1]
    assert rec.doi == ""
    assert rec.title == "Second Paper"


def test_empty_text_gives_no_records():
    assert parse_ris_text("") == []
