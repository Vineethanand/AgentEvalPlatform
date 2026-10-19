"""The harness adapter contract.

A harness (Hermes, the baseline loop, ...) is plugged in by writing ONE class that
implements prepare / run / collect. The platform core never branches on harness names.

Data flow for one trial:

1. The worker writes ``ctx.json`` (a :class:`TrialContext`) into the trial folder.
2. Inside the sandbox, ``adapters/run.py`` loads it, calls ``prepare`` then ``run`` then ``collect``
   on the adapter, and writes ``events.jsonl`` (via :class:`EventSink`), ``result.json``
   (a :class:`RunResult`) and ``artifacts.json``.
3. The worker reads those files back after the sandbox exits; it never imports the adapter.

This module is stdlib-only because it runs inside the sandbox container.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
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
        """Memory setting of this config: "off" (default), "on", or "carry" (kept from the previous trial)."""
        return (self.settings.get("memory") or {}).get("mode", "off")

    @property
    def max_steps(self) -> int:
        """Most model calls (steps) the harness may make before it must stop."""
        return int(self.settings.get("max_steps", 25))

    @property
    def temperature(self) -> float:
        """Sampling temperature from the config (harnesses that cannot set it ignore it)."""
        return float(self.settings.get("temperature", 0.7))

    @classmethod
    def load(cls, path: Path) -> "TrialContext":
        """Read a ctx.json written by the worker. Paths are stored as strings, so turn them back into Paths."""
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        for k in ("workspace", "home", "trial_dir", "skills_dir"):
            if d.get(k):
                d[k] = Path(d[k])
        return cls(**d)

    def dump(self, path: Path) -> None:
        """Write this context as JSON (Paths become strings) for the process inside the sandbox to load."""
        d = {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items()}
        Path(path).write_text(json.dumps(d, indent=2), encoding="utf-8")


@dataclass
class RunResult:
    """What a harness reports after a run. Written to result.json; the worker turns it into the trial record."""

    final_answer: str = ""
    # completed | step_budget | token_budget | timeout | harness_error | gave_up
    stop_reason: str = "completed"
    steps: int = 0
    tokens_in: int = 0      # as reported by the harness; the gateway's numbers win when available
    tokens_out: int = 0
    # Cost the harness itself reports (Claude Code's CLI does). Used only when there is no gateway spend log.
    cost_usd: float | None = None
    error: str | None = None


class EventSink:
    """Appends normalised trace events to events.jsonl as they happen.

    Event types: llm_call, tool_call, tool_result, memory_read, memory_write,
    skill_invoked, agent_message, harness_note.
    """

    def __init__(self, path: Path):
        """Create the log file's folder; ``seq`` numbers the events in order, starting at 1."""
        self.path = Path(path)
        self.seq = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, payload: dict[str, Any] | None = None, parent_seq: int | None = None) -> int:
        """Append one event and return its sequence number.

        ``parent_seq`` links an event to the one that caused it (a tool_result points at its tool_call, a
        tool_call at the llm_call that asked for it), which lets the UI draw the trace as a tree. The file is
        opened for every event, so a crash or kill never loses events that were already written.
        """
        self.seq += 1
        ev = {
            "seq": self.seq,
            "parent_seq": parent_seq,
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, default=str) + "\n")
        return self.seq


class HarnessAdapter(ABC):
    """Base class every harness adapter implements; see the module docstring for the contract."""

    name: ClassVar[str]
    version: ClassVar[str] = "0.1.0"
    capabilities: ClassVar[set[str]] = set()

    @abstractmethod
    def prepare(self, ctx: TrialContext) -> None:
        """Turn the config into the harness's native setup: config files, skills, memory."""

    @abstractmethod
    def run(self, ctx: TrialContext, sink: EventSink) -> RunResult:
        """Run the task to completion or budget. Emit an event for every step."""

    def collect(self, ctx: TrialContext) -> dict[str, Any]:  # pylint: disable=unused-argument
        """Return extra artifacts (e.g. memory files after the run). Optional; the default returns nothing."""
        return {}

    @staticmethod
    def out_of_time(ctx: TrialContext) -> bool:
        """True once the trial's deadline has passed (a deadline of 0 means no limit)."""
        return bool(ctx.deadline) and time.time() > ctx.deadline
