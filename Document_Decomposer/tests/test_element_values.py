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


def test_negative_number_is_skipped_not_flipped():
    assert parse_values("samples were cooled to -10 °C overnight") == []


def test_label_h_false_positive_is_known_and_bounded():
    # Known accepted FP: "Table 4 h" may yield an 'h' value; the real value must
    # still be extracted and the caller's condition-facet gate bounds the damage.
    vals = parse_values("see Table 4 h for details at 400 rpm")
    units = {v["unit"] for v in vals}
    assert "rpm" in units


def test_no_space_between_number_and_unit():
    vals = parse_values("pressures up to 25MPa were applied")
    assert vals and vals[0]["unit"] == "MPa" and vals[0]["num"] == "25"
