from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .. import engine_bridge

engine_bridge.ensure_engine_write_on_path()  # adds Document_Decomposer/scripts/write to sys.path

import run_writing_loop as _wl  # engine module (now importable)  # noqa: E402

_AUTHOR_HINT = 'Respond with JSON: {"draft_markdown":"","claim_register":[],"self_check":{}}'


class AIClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        ...


def run_writing_round(
    brief: dict[str, Any],
    run_dir: Path,
    round_index: int,
    revision_history: list[dict[str, Any]],
    author_client: AIClient,
    expert_client: AIClient,
) -> dict[str, Any]:
    """One writing round, replicating the engine main-loop body with injected clients.

    author draft -> mechanical gates -> (citation-only? deterministic repair) ->
    if gates fail: mechanical revision plan (experts skipped); else 4 expert reviews
    + adjudicator/acceptance gate. Returns {decision, draft_path, reviews}.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    round_label = f"v{round_index:02d}"
    payload = {"brief": brief, "previous_reviews_and_revision_plans": revision_history, "round": round_index}

    draft_obj = _wl.call_json(
        author_client, _wl.read_text(_wl.PROMPTS / "author_deepseek.md"),
        payload, _AUTHOR_HINT, run_dir / f"input_author_{round_label}.json",
    )
    draft_path = _wl.write_author_round(run_dir, round_index, draft_obj)
    draft_text = _wl.read_text(draft_path)
    gate_result = _wl.mechanical_gates(brief, draft_text, draft_obj)
    _wl.write_json(run_dir / f"mechanical_gates_{round_label}.json", gate_result)

    active_obj, active_path, active_gate = draft_obj, draft_path, gate_result
    if _wl.is_citation_only_failure(gate_result):
        active_obj, active_path, active_gate = _wl.repair_citations(
            author_client, run_dir, round_label, brief, draft_obj, gate_result,
        )

    if not active_gate.get("passed"):
        reviews: list[dict[str, Any]] = []
        decision = _wl.mechanical_revision_plan(active_gate)
        decision.setdefault("gate_decision", "continue")
    else:
        reviews = _wl.review_experts(
            expert_client, run_dir, round_index, brief,
            _wl.read_text(active_path), active_obj, active_gate,
        )
        decision = _wl.build_revision_plan(expert_client, run_dir, round_index, reviews)
        decision["gate_decision"] = _wl.decide_gate(reviews)

    _wl.write_json(run_dir / f"decision_{round_label}.json", decision)
    return {"decision": decision, "draft_path": str(active_path), "reviews": reviews}


def run_writing_loop(
    brief: dict[str, Any],
    run_dir: Path,
    max_rounds: int,
    author_client: AIClient,
    expert_client: AIClient,
) -> dict[str, Any]:
    """Run rounds until internal acceptance or max_rounds. Returns a summary."""
    history: list[dict[str, Any]] = []
    status = "continue"
    for round_index in range(1, max_rounds + 1):
        result = run_writing_round(
            brief, run_dir, round_index, history, author_client, expert_client,
        )
        history.append({"round": round_index, **result})
        if result["decision"].get("gate_decision") == "internal_acceptance_gate":
            status = "internal_acceptance_gate"
            break
    return {"status": status, "rounds": len(history), "history": history}
