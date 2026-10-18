"""Failure taxonomy: one primary category per failed trial, decided by simple rules.

Rules are cheap and auditable. Order matters: the first matching rule wins.
"""
from __future__ import annotations

import json
import re
from typing import Any

GIVE_UP = re.compile(r"\b(cannot|can't|unable to|i don't know|not possible|give up)\b", re.I)


def classify(*, status: str, stop_reason: str, passed: bool | None, events: list[dict[str, Any]],
             task: dict[str, Any], grades: list[dict[str, Any]], max_steps: int, final_answer: str) -> str | None:
    if status in ("infra_error", "harness_error") or stop_reason == "harness_error":
        return "infra_error"
    if passed:
        return None
    if stop_reason in ("step_budget", "token_budget", "timeout"):
        return "budget_exhausted"

    calls = [e for e in events if e.get("type") == "tool_call"]
    # Loop: the same tool with identical arguments 3+ times in a row.
    run = 1
    for prev, cur in zip(calls, calls[1:]):
        same = prev["payload"].get("tool") == cur["payload"].get("tool") and \
            json.dumps(prev["payload"].get("arguments")) == json.dumps(cur["payload"].get("arguments"))
        run = run + 1 if same else 1
        if run >= 3:
            return "loop"

    results = [e for e in events if e.get("type") == "tool_result"]
    if any(r["payload"].get("schema_valid") is False for r in results) or \
            any("invalid_tool_call" in (e.get("payload") or {}) for e in events):
        return "hallucinated_tool_or_args"

    used = {c["payload"].get("tool") for c in calls}
    required = set(task.get("required_tools") or [])
    if required and not (required & used):
        return "wrong_tool"

    tags = set(task.get("tags") or [])
    if "memory" in tags and not any(e.get("type") == "memory_read" for e in events):
        return "ignored_memory"
    if "skill" in tags and not any(e.get("type") == "skill_invoked" for e in events):
        return "ignored_skill"

    steps = sum(1 for e in events if e.get("type") == "llm_call")
    if steps < max(2, max_steps // 4) and GIVE_UP.search(final_answer or "") and \
            "cannot determine" not in str(task.get("graders")):
        return "gave_up_early"

    if len({g["passed"] for g in grades}) > 1:
        return "grader_disagreement"
    return "wrong_answer"
