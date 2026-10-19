"""LLM judge with a rubric of yes/no criteria.

Design choices (see docs/design.md, "LLM judge"):
- Rubric = 4-6 binary criteria marked must / nice. Pass = every "must" is yes.
- The judge sees the task, rubric, final answer and the files the agent produced.
  It does NOT see the agent's reasoning, so it can't be talked into a pass.
- For each criterion it writes a reason BEFORE the verdict.
- Backend: the gateway (default; model = alias in JUDGE_MODEL, temperature 0) or the `claude` CLI
  (JUDGE_BACKEND=claude-cli, or `backend: claude-cli` on the task's grader; model = JUDGE_CLI_MODEL, default haiku).
  Use one judge for a whole experiment, ideally from a different provider than the agent models.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..adapters.llm import LLMError, chat
from . import claude_cli

if TYPE_CHECKING:
    from . import GradeInput

JUDGE_PROMPT = """You are grading an AI agent's work against a rubric. Be strict and literal.

## Task given to the agent
{task}

## Agent's final answer
{answer}

## Files the agent produced or changed
{files}

## Rubric
{rubric}

For EACH criterion, first write a one-sentence reason citing the evidence, then a verdict "yes" or "no".
If the evidence is missing, the verdict is "no".
Reply with JSON only, in exactly this shape:
{{"criteria": [{{"id": "<id>", "reason": "<reason>", "verdict": "yes" | "no"}}]}}"""


def _files_snapshot(workspace: Path, include: list[str] | None, limit: int = 12000) -> str:
    parts, used = [], 0
    paths = [workspace / p for p in include] if include else sorted(p for p in workspace.rglob("*") if p.is_file())
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        text = p.read_text(errors="replace")
        chunk = f"### {p.relative_to(workspace)}\n{text}\n"
        if used + len(chunk) > limit:
            parts.append(f"### {p.relative_to(workspace)}\n[omitted: size limit]\n")
            continue
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts) or "(none)"


def _parse(content: str) -> dict:
    m = re.search(r"\{.*\}", content or "", re.S)
    if not m:
        raise ValueError("judge did not return JSON")
    return json.loads(m.group(0))


def llm_judge(inp: "GradeInput", spec: dict[str, Any]) -> dict[str, Any]:
    rubric = spec["rubric"]
    rubric_text = "\n".join(f"- id={c['id']} ({'MUST' if c.get('must', True) else 'nice'}): {c['text']}" for c in rubric)
    prompt = JUDGE_PROMPT.format(
        task=inp.task["prompt"], answer=inp.final_answer or "(empty)",
        files=_files_snapshot(inp.workspace, spec.get("files")), rubric=rubric_text,
    )
    backend = spec.get("backend") or os.environ.get("JUDGE_BACKEND", "gateway")
    use_cli = backend == "claude-cli"
    model = (spec.get("model") or os.environ.get("JUDGE_CLI_MODEL", "haiku")) if use_cli         else spec.get("model") or os.environ.get("JUDGE_MODEL", "gpt-judge")
    base = os.environ.get("GATEWAY_URL", "http://localhost:4000")
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    prices = spec.get("_judge_prices") or {}
    cost, last_err = 0.0, None
    for _ in range(3):  # retry malformed JSON
        try:
            if use_cli:
                text, u = claude_cli.ask(prompt, model)
                resp = {"choices": [{"message": {"content": text}}]}
            else:
                resp = chat(base, key, model, [{"role": "user", "content": prompt}], temperature=0.0)
                u = resp.get("usage") or {}
        except (LLMError, claude_cli.CliJudgeError) as e:
            last_err = e
            continue
        cost += (u.get("prompt_tokens", 0) * prices.get("in", 0) + u.get("completion_tokens", 0) * prices.get("out", 0)) / 1e6
        try:
            verdicts = {c["id"]: c for c in _parse(resp["choices"][0]["message"]["content"])["criteria"]}
            break
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            last_err = e
    else:
        return {"score": 0.0, "passed": False, "reasoning": f"ungraded: judge failed ({last_err})",
                "raw": {"ungraded": True}, "judgeCostUsd": cost}

    checks = []
    for c in rubric:
        v = verdicts.get(c["id"], {})
        checks.append({"name": c["id"], "passed": str(v.get("verdict", "no")).lower() == "yes",
                       "detail": v.get("reason", "no verdict"), "must": c.get("must", True)})
    must = [c for c in checks if c["must"]]
    passed = all(c["passed"] for c in must)
    return {
        "score": sum(c["passed"] for c in checks) / len(checks),
        "passed": passed,
        "reasoning": "; ".join(f"{c['name']}={'yes' if c['passed'] else 'no'}: {c['detail']}" for c in checks),
        "raw": {"checks": checks, "judge_model": model, "judge_backend": backend},
        "judgeCostUsd": cost,
    }
