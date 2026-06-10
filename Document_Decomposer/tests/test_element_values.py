from docdecomp.element_values import parse_values


def test_single_value_with_unit():
    vals = parse_values("measured at 333 K up to 25 MPa")
    assert {"raw": "333 K", "num": "333", "unit": "K"} in vals
    assert {"raw": "25 MPa", "num": "25", "unit": "MPa"} in vals


def test_range_value():
    vals = parse_values("pressures of 0.1-30 MPa were applied")
    assert vals[0]["num"] == "0.1-30"
    assert vals[0]["unit"] == "MPa"


def test_decimal_and_rpm_and_hours():
    vals = parse_values("ball-milled for 4 h at 400 rpm")
    units = {v["unit"] for v in vals}
    assert units == {"h", "rpm"}


def test_no_number_returns_empty():
    assert parse_values("under nitrogen atmosphere") == []
