"""Failure taxonomy: one primary category per failed trial, decided by simple rules.

Rules are cheap and auditable. Order matters: the first matching rule wins.
"""
from __future__ import annotations

import json
import re
from typing import Any

GIVE_UP = re.compile(r"\b(cannot|can't|unable to|i don't know|not possible|give up)\b", re.I)


def _repeats_same_call(calls: list[dict[str, Any]], times: int = 3) -> bool:
    """True if the same tool was called with identical arguments ``times`` or more times in a row."""
    run = 1
    for prev, cur in zip(calls, calls[1:]):
        same = prev["payload"].get("tool") == cur["payload"].get("tool") and \
            json.dumps(prev["payload"].get("arguments")) == json.dumps(cur["payload"].get("arguments"))
        run = run + 1 if same else 1
        if run >= times:
            return True
    return False


def classify(  # pylint: disable=too-many-return-statements
             *, status: str, stop_reason: str, passed: bool | None, events: list[dict[str, Any]],
             task: dict[str, Any], grades: list[dict[str, Any]], max_steps: int, final_answer: str) -> str | None:
    """Return the failure category for a trial, or None if it passed.

    Rules in priority order (the first match wins):
      1. infra_error: the sandbox or the harness itself broke, so the model is not to blame.
      2. (passed) no category.
      3. budget_exhausted: stopped by the step, token or time limit.
      4. loop: the same tool call with the same arguments three times in a row.
      5. hallucinated_tool_or_args: a call to an unknown tool, or arguments that were not valid.
      6. wrong_tool: the task lists required tools and none of them was used.
      7. ignored_memory / ignored_skill: a memory (or skill) task where the agent never read memory
         (or never used a skill), which is what the task was designed to test.
      8. gave_up_early: a short run that ends in "cannot / unable to ..." although the task has an answer.
      9. grader_disagreement: the graders did not agree with each other, so the label is uncertain.
     10. wrong_answer: everything else.
    """
    if status in ("infra_error", "harness_error") or stop_reason == "harness_error":
        return "infra_error"
    if passed:
        return None
    if stop_reason in ("step_budget", "token_budget", "timeout"):
        return "budget_exhausted"

    calls = [e for e in events if e.get("type") == "tool_call"]
    if _repeats_same_call(calls):
        return "loop"

    results = [e for e in events if e.get("type") == "tool_result"]
    if any(r["payload"].get("schema_valid") is False for r in results) or \
            any("invalid_tool_call" in (e.get("payload") or {}) for e in events):
        return "hallucinated_tool_or_args"

    used = {c["payload"].get("tool") for c in calls}
    required = set(task.get("required_tools") or [])
    if required and not required & used:
        return "wrong_tool"

    tags = set(task.get("tags") or [])
    if "memory" in tags and not any(e.get("type") == "memory_read" for e in events):
        return "ignored_memory"
    if "skill" in tags and not any(e.get("type") == "skill_invoked" for e in events):
        return "ignored_skill"

    # "Early" means fewer model calls than a quarter of the step budget (and at least 2). Tasks whose correct
    # answer is itself "cannot determine" are excluded, since giving up is the right behaviour there.
    steps = sum(1 for e in events if e.get("type") == "llm_call")
    if steps < max(2, max_steps // 4) and GIVE_UP.search(final_answer or "") and \
            "cannot determine" not in str(task.get("graders")):
        return "gave_up_early"

    if len({g["passed"] for g in grades}) > 1:
        return "grader_disagreement"
    return "wrong_answer"
