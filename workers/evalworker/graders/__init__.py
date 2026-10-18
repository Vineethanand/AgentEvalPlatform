"""Grader registry. Every grader returns the same shape:

    {"grader": str, "primary": bool, "score": 0..1, "passed": bool, "reasoning": str,
     "raw": {"checks": [...]}, "judgeCostUsd": float}

A task lists its graders in task.yaml; the one marked primary decides pass/fail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .deterministic import exact_match, state_check, trace_check, unit_test
from .llm_judge import llm_judge


@dataclass
class GradeInput:
    task: dict[str, Any]          # parsed task.yaml
    task_dir: Path                # tasks/<id>/
    workspace: Path               # final workspace after the agent ran
    final_answer: str
    events: list[dict[str, Any]] = field(default_factory=list)


GRADERS: dict[str, Callable[[GradeInput, dict[str, Any]], dict[str, Any]]] = {
    "exact_match": exact_match,
    "unit_test": unit_test,
    "state_check": state_check,
    "trace_check": trace_check,
    "llm_judge": llm_judge,
}


def grade_all(inp: GradeInput, skip_judge: bool = False) -> list[dict[str, Any]]:
    specs = inp.task.get("graders") or []
    if specs and not any(g.get("primary") for g in specs):
        specs[0] = {**specs[0], "primary": True}
    out = []
    for spec in specs:
        kind = spec["type"]
        if skip_judge and kind == "llm_judge":
            continue
        try:
            g = GRADERS[kind](inp, spec)
        except Exception as e:  # noqa: BLE001 - a broken grader must never look like a pass
            g = {"score": 0.0, "passed": False, "reasoning": f"grader error: {e!r}", "raw": {"grader_error": True}}
        g.setdefault("judgeCostUsd", 0.0)
        out.append({"grader": kind, "primary": bool(spec.get("primary")), **g})
    return out


def primary(grades: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((g for g in grades if g["primary"]), grades[0] if grades else None)
