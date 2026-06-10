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
