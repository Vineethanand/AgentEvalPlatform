"""The harness adapter contract.

A harness (Hermes, the baseline loop, ...) is plugged in by writing ONE class that
implements prepare / run / collect. The platform core never branches on harness names.

This module is stdlib-only because it runs inside the sandbox container.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class TrialContext:
    """Everything a harness needs for one trial. Written by the worker as ctx.json."""

    trial_id: str
    attempt: int
    prompt: str
    workspace: Path          # the task's fixtures, fresh copy; the agent works here
    home: Path               # harness state (memory, skills, config). Fresh unless memory mode = carry
    trial_dir: Path          # where events.jsonl / result.json / native logs go
    model: str               # gateway alias, e.g. "claude-sonnet"
    gateway_url: str         # OpenAI-compatible base URL, e.g. http://gateway:4000
    api_key: str             # per-trial gateway key
    seed: int
    settings: dict[str, Any]
    skills_dir: Path | None = None   # bundled skills available to install
    deadline: float = 0.0            # unix time after which the run must stop

    @property
    def memory_mode(self) -> str:
        return (self.settings.get("memory") or {}).get("mode", "off")

    @property
    def max_steps(self) -> int:
        return int(self.settings.get("max_steps", 25))

    @property
    def temperature(self) -> float:
        return float(self.settings.get("temperature", 0.7))

    @classmethod
    def load(cls, path: Path) -> "TrialContext":
        d = json.loads(Path(path).read_text())
        for k in ("workspace", "home", "trial_dir", "skills_dir"):
            if d.get(k):
                d[k] = Path(d[k])
        return cls(**d)

    def dump(self, path: Path) -> None:
        d = {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items()}
        Path(path).write_text(json.dumps(d, indent=2))


@dataclass
class RunResult:
    final_answer: str = ""
    # completed | step_budget | token_budget | timeout | harness_error | gave_up
    stop_reason: str = "completed"
    steps: int = 0
    tokens_in: int = 0      # as reported by the harness; the gateway's numbers win when available
    tokens_out: int = 0
    cost_usd: float | None = None   # cost the harness itself reports (Claude Code's CLI does); used when there is no gateway spend log
    error: str | None = None


class EventSink:
    """Appends normalised trace events to events.jsonl as they happen.

    Event types: llm_call, tool_call, tool_result, memory_read, memory_write,
    skill_invoked, agent_message, harness_note.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.seq = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, type: str, payload: dict[str, Any] | None = None, parent_seq: int | None = None) -> int:
        self.seq += 1
        ev = {
            "seq": self.seq,
            "parent_seq": parent_seq,
            "type": type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, default=str) + "\n")
        return self.seq


class HarnessAdapter(ABC):
    name: ClassVar[str]
    version: ClassVar[str] = "0.1.0"
    capabilities: ClassVar[set[str]] = set()

    @abstractmethod
    def prepare(self, ctx: TrialContext) -> None:
        """Turn the config into the harness's native setup: config files, skills, memory."""

    @abstractmethod
    def run(self, ctx: TrialContext, sink: EventSink) -> RunResult:
        """Run the task to completion or budget. Emit an event for every step."""

    def collect(self, ctx: TrialContext) -> dict[str, Any]:
        """Return extra artifacts (e.g. memory files after the run). Optional."""
        return {}

    @staticmethod
    def out_of_time(ctx: TrialContext) -> bool:
        return bool(ctx.deadline) and time.time() > ctx.deadline
