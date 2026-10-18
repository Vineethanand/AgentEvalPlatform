"""Hermes Agent adapter (Nous Research, https://github.com/NousResearch/hermes-agent).

Hermes keeps its state under HERMES_HOME: memory in MEMORY.md / USER.md, skills as
SKILL.md folders, sessions in SQLite. We point HERMES_HOME at the trial's home dir,
so every trial starts clean unless the config's memory mode is "carry".

VERIFY ON DAY 1 (Hermes changes quickly; these are assumptions to confirm):
  1. Entry point: `from run_agent import AIAgent` and
     `AIAgent(...).run_conversation(user_message) -> dict` with "final_response" and
     "messages". The adapter only passes keyword args the installed AIAgent accepts.
  2. Memory can be switched off by disabling the "memory" toolset.
  3. Skills are read from $HERMES_HOME/skills/<name>/SKILL.md.
If the API differs, only this file changes.
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import threading
from pathlib import Path

from .base import EventSink, HarnessAdapter, RunResult, TrialContext

MEMORY_FILES = ("MEMORY.md", "USER.md")


def _read_memory(home: Path) -> dict[str, str]:
    out = {}
    for name in MEMORY_FILES:
        for p in (home / name, home / "memories" / name):
            if p.exists():
                out[str(p.relative_to(home))] = p.read_text(errors="replace")
    return out


class HermesAdapter(HarnessAdapter):
    name = "hermes"
    version = "0.1.0"
    capabilities = {"tools", "temperature", "max_steps", "memory", "skills"}

    def prepare(self, ctx: TrialContext) -> None:
        ctx.home.mkdir(parents=True, exist_ok=True)
        os.environ["HERMES_HOME"] = str(ctx.home)
        # Route all model calls through the gateway with the per-trial key.
        os.environ["OPENAI_BASE_URL"] = ctx.gateway_url.rstrip("/") + "/v1"
        os.environ["OPENAI_API_KEY"] = ctx.api_key
        if ctx.memory_mode == "off":
            for f in MEMORY_FILES:
                (ctx.home / f).unlink(missing_ok=True)
                (ctx.home / "memories" / f).unlink(missing_ok=True)
        for s in [s.split("@")[0] for s in ctx.settings.get("skills") or []]:
            src = ctx.skills_dir / s if ctx.skills_dir else None
            if src and src.exists():
                shutil.copytree(src, ctx.home / "skills" / s, dirs_exist_ok=True)
        self.memory_before = _read_memory(ctx.home)

    def _make_agent(self, ctx: TrialContext):
        from run_agent import AIAgent  # installed in the harness-hermes image

        wanted = {
            "base_url": ctx.gateway_url.rstrip("/") + "/v1",
            "api_key": ctx.api_key,
            "model": ctx.model,
            "max_iterations": ctx.max_steps,
            "temperature": ctx.temperature,
            "quiet_mode": True,
            "save_trajectories": False,
            "disabled_toolsets": ["memory"] if ctx.memory_mode == "off" else None,
        }
        accepted = inspect.signature(AIAgent.__init__).parameters
        kwargs = {k: v for k, v in wanted.items() if k in accepted and v is not None}
        self.ignored_settings = sorted(k for k, v in wanted.items() if k not in accepted and v is not None)
        return AIAgent(**kwargs)

    def run(self, ctx: TrialContext, sink: EventSink) -> RunResult:
        result = RunResult()
        try:
            agent = self._make_agent(ctx)
        except Exception as e:
            result.stop_reason, result.error = "harness_error", f"could not start Hermes: {e!r}"
            sink.emit("harness_note", {"error": result.error})
            return result
        if self.ignored_settings:
            sink.emit("harness_note", {"settings_not_supported_by_installed_hermes": self.ignored_settings})
            if "disabled_toolsets" in self.ignored_settings and ctx.memory_mode == "off":
                # Memory off could not be enforced: fail loudly instead of comparing the wrong thing.
                result.stop_reason, result.error = "harness_error", "cannot disable Hermes memory with this Hermes version"
                return result

        cwd = os.getcwd()
        os.chdir(ctx.workspace)
        out: dict = {}
        err: list[BaseException] = []

        def target():
            try:
                out.update(agent.run_conversation(ctx.prompt) or {})
            except BaseException as e:  # noqa: BLE001
                err.append(e)

        th = threading.Thread(target=target, daemon=True)
        th.start()
        th.join(timeout=max(1.0, ctx.deadline - __import__("time").time()) if ctx.deadline else None)
        os.chdir(cwd)
        if th.is_alive():
            result.stop_reason = "timeout"
        elif err:
            result.stop_reason, result.error = "harness_error", repr(err[0])

        messages = out.get("messages") or []
        self._emit_messages(messages, sink, result)
        result.final_answer = str(out.get("final_response") or "").strip()
        if result.stop_reason == "completed" and result.steps >= ctx.max_steps and not result.final_answer:
            result.stop_reason = "step_budget"

        (ctx.trial_dir / "native").mkdir(exist_ok=True)
        (ctx.trial_dir / "native" / "hermes_result.json").write_text(json.dumps(out, indent=2, default=str))

        # Confirm memory activity by diffing the memory files (catches writes the trace missed).
        after = _read_memory(ctx.home)
        for k in sorted(set(after) | set(self.memory_before)):
            if after.get(k) != self.memory_before.get(k):
                sink.emit("memory_write", {"store": k, "source": "file_diff", "after": after.get(k)})
        return result

    def _emit_messages(self, messages: list[dict], sink: EventSink, result: RunResult) -> None:
        """Translate Hermes's OpenAI-style message list into normalised events."""
        call_seq: dict[str, int] = {}
        for m in messages:
            role = m.get("role")
            if role == "assistant":
                result.steps += 1
                seq = sink.emit("llm_call", {"step": result.steps, "response": {"content": m.get("content"), "tool_calls": m.get("tool_calls")}})
                if m.get("content"):
                    sink.emit("agent_message", {"role": "assistant", "content": m.get("content")}, parent_seq=seq)
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    name = fn.get("name", "")
                    tseq = sink.emit("tool_call", {"tool": name, "arguments": fn.get("arguments")}, parent_seq=seq)
                    call_seq[tc.get("id", "")] = tseq
                    if "memory" in name:
                        kind = "memory_read" if any(w in name for w in ("read", "search", "recall")) else "memory_write"
                        sink.emit(kind, {"store": "hermes", "tool": name, "arguments": fn.get("arguments")}, parent_seq=tseq)
                    if "skill" in name:
                        sink.emit("skill_invoked", {"tool": name, "arguments": fn.get("arguments")}, parent_seq=tseq)
            elif role == "tool":
                content = m.get("content")
                sink.emit("tool_result", {"tool": m.get("name"), "output": str(content)[:16000],
                                          "error": "error" in str(content)[:200].lower()},
                          parent_seq=call_seq.get(m.get("tool_call_id", "")))

    def collect(self, ctx: TrialContext) -> dict:
        return {"memory_after": _read_memory(ctx.home)}
