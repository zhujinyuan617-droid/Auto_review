from pathlib import Path

from _fake_ai import SequencedFakeClient

from autoreview_app.writing.loop import run_writing_loop, run_writing_round

BRIEF = {"claim_catalog": [{"claim_id": "C1"}], "topic": "methane"}

CLEAN_DRAFT = {
    "draft_markdown": "Adsorption increases with pressure [S09].",
    "claim_register": [{"claim": "adsorption rises", "support_text": "the study shows", "claim_ids": ["C1"]}],
    "self_check": {},
}


def _accept_review():
    return {"decision": "accept", "scores": {"overall": 5}, "fatal_issues": [], "major_issues": [],
            "minor_issues": [], "strengths": ["clear"], "summary": "ok"}


def test_round_reaches_acceptance(tmp_path: Path):
    author = SequencedFakeClient([CLEAN_DRAFT])
    experts = SequencedFakeClient([_accept_review() for _ in range(4)])

    result = run_writing_round(
        brief=BRIEF, run_dir=tmp_path, round_index=1, revision_history=[],
        author_client=author, expert_client=experts,
    )

    assert author.call_count == 1
    assert experts.call_count == 4
    assert result["decision"]["gate_decision"] == "internal_acceptance_gate"
    assert Path(result["draft_path"]).exists()


def test_round_mechanical_failure_skips_experts(tmp_path: Path):
    bad_draft = {"draft_markdown": "Adsorption is 42 units high [S09].", "claim_register": [], "self_check": {}}
    author = SequencedFakeClient([bad_draft])
    experts = SequencedFakeClient([])

    result = run_writing_round(
        brief=BRIEF, run_dir=tmp_path, round_index=1, revision_history=[],
        author_client=author, expert_client=experts,
    )

    assert experts.call_count == 0
    assert result["decision"]["gate_decision"] != "internal_acceptance_gate"


def test_loop_stops_at_acceptance(tmp_path: Path):
    author = SequencedFakeClient([CLEAN_DRAFT, CLEAN_DRAFT, CLEAN_DRAFT])
    experts = SequencedFakeClient([_accept_review() for _ in range(12)])

    summary = run_writing_loop(
        brief=BRIEF, run_dir=tmp_path, max_rounds=3,
        author_client=author, expert_client=experts,
    )

    assert summary["status"] == "internal_acceptance_gate"
    assert summary["rounds"] == 1
