from autoreview_app.writing.gates import check_draft


def test_clean_draft_passes_citation_gate():
    draft = "Methane adsorption increases with pressure [S09]. Carbon capture follows [S12]."
    result = check_draft(draft)
    assert result["citation"]["passed"] is True


def test_bare_paper_id_fails_citation_gate():
    draft = "Methane adsorption increases with pressure S09."
    result = check_draft(draft)
    assert result["citation"]["passed"] is False
    assert any("S09" in str(x) for x in result["citation"]["bare_paper_ids"])


def test_adjacent_citation_blocks_fail():
    draft = "This is supported by multiple works [S09][S108]."
    result = check_draft(draft)
    assert result["citation"]["passed"] is False
    assert result["citation"]["adjacent_bracketed_citation_groups"]


def test_style_gate_flags_generic_research_needed():
    draft = "More research is needed to understand this fully."
    result = check_draft(draft)
    assert result["style"]["warnings"]


def test_clean_draft_has_no_style_warnings():
    draft = "Methane adsorption increases with pressure [S09]."
    result = check_draft(draft)
    assert result["style"]["warnings"] == []
