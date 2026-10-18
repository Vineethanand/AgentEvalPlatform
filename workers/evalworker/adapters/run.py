"""Entry point that runs INSIDE the sandbox: python -m evalworker.adapters.run <ctx.json> <harness>

Writes events.jsonl, result.json and artifacts.json into the trial dir. Never raises:
any crash becomes stop_reason=harness_error so the worker can classify it.
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import asdict
from pathlib import Path

from . import get_adapter
from .base import EventSink, RunResult, TrialContext


def main(ctx_path: str, harness: str) -> int:
    ctx = TrialContext.load(Path(ctx_path))
    sink = EventSink(ctx.trial_dir / "events.jsonl")
    result = RunResult()
    artifacts: dict = {}
    try:
        adapter = get_adapter(harness)
        adapter.prepare(ctx)
        result = adapter.run(ctx, sink)
        artifacts = adapter.collect(ctx)
        artifacts["adapter"] = {"name": adapter.name, "version": adapter.version}
    except Exception as e:  # noqa: BLE001
        result.stop_reason = "harness_error"
        result.error = f"{e!r}\n{traceback.format_exc()}"
        sink.emit("harness_note", {"error": result.error})
    (ctx.trial_dir / "result.json").write_text(json.dumps(asdict(result), indent=2))
    (ctx.trial_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
