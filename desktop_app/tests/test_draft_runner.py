from pathlib import Path

import autoreview_app.writing.draft_runner as dr


def test_run_draft_orchestrates_and_reads_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "build_brief_via_engine", lambda sel, run_dir: {"topic": sel.get("topic")})

    def fake_loop(brief, run_dir, max_rounds, author_client, expert_client):
        run_dir.mkdir(parents=True, exist_ok=True)
        draft = run_dir / "draft_v01.md"
        draft.write_text("# Section\nGrounded body.", encoding="utf-8")
        return {"status": "internal_acceptance_gate", "rounds": 1,
                "history": [{"round": 1, "draft_path": str(draft), "decision": {}, "reviews": []}]}

    monkeypatch.setattr(dr, "run_writing_loop", fake_loop)

    msgs = []
    out = dr.run_draft({"topic": "methane", "paper_ids": ["S09"]}, tmp_path / "library",
                       lambda: object(), msgs.append)
    assert out["status"] == "internal_acceptance_gate"
    assert out["draft_text"] == "# Section\nGrounded body."
    assert "building brief" in msgs and "done" in msgs


def test_run_draft_handles_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "build_brief_via_engine", lambda sel, run_dir: {})
    monkeypatch.setattr(dr, "run_writing_loop",
                        lambda *a, **k: {"status": "continue", "rounds": 0, "history": []})
    out = dr.run_draft({"topic": "x"}, tmp_path / "library", lambda: object(), lambda m: None)
    assert out["draft_text"] == ""
