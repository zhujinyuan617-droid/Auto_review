from docdecomp.element_quotes import verify_quote

BLOCK = "The montmorillonite was ball-milled for 4 h at 400 rpm under N2 atmosphere."


def test_exact_quote_passes_both_levels():
    r = verify_quote("ball-milled for 4 h at 400 rpm", BLOCK)
    assert r["quote_verified"] is True
    assert r["digits_verified"] is True


def test_whitespace_and_case_tolerated():
    r = verify_quote("Ball-Milled   for 4 h\nat 400 rpm", BLOCK)
    assert r["quote_verified"] is True
    assert r["digits_verified"] is True


def test_changed_digit_fails_digits_but_passes_loose():
    r = verify_quote("ball-milled for 5 h at 400 rpm", BLOCK)
    assert r["quote_verified"] is True
    assert r["digits_verified"] is False


def test_fabricated_quote_fails():
    r = verify_quote("the sample was acid-washed in HCl overnight", BLOCK)
    assert r["quote_verified"] is False
    assert r["reason"] == "not_found"


def test_ellipsis_fragments_each_checked():
    r = verify_quote("The montmorillonite was ball-milled ... under N2 atmosphere", BLOCK)
    assert r["quote_verified"] is True


def test_too_short_rejected():
    r = verify_quote("4 h", BLOCK)
    assert r["quote_verified"] is False
    assert r["reason"] == "too_short"


def test_ellipsis_with_missing_fragment_fails():
    r = verify_quote("The montmorillonite was ball-milled ... acid washed overnight in HCl", BLOCK)
    assert r["quote_verified"] is False
    assert r["reason"] == "not_found"


def test_ellipsis_with_digit_changed_fragment_fails_digits_only():
    r = verify_quote("The montmorillonite was ball-milled ... for 9 h at 400 rpm under N2", BLOCK)
    assert r["quote_verified"] is True
    assert r["digits_verified"] is False


def test_micro_sign_variants_match():
    block = "pore diameters of 5 μm were observed in the matrix samples"
    r = verify_quote("pore diameters of 5 µm were observed", block)
    assert r["quote_verified"] is True
    assert r["digits_verified"] is True
