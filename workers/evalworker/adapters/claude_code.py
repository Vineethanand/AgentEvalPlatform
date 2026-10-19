"""Claude Code adapter: drives the official `claude` CLI headless (`claude -p ... --output-format stream-json`).

Unlike baseline/Hermes this harness does NOT go through the LiteLLM gateway: the CLI talks to
Anthropic directly and authenticates with a subscription token (CLAUDE_CODE_OAUTH_TOKEN, from
`claude setup-token`). The "model" of the config only selects the Claude model (sonnet/opus/haiku,
or a full claude-* id via settings.cli_model). Token counts come from the CLI's own result event.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from .base import EventSink, HarnessAdapter, RunResult, TrialContext

TOOLS = "Read,Write,Edit,Glob,Grep,Bash"


def _cli_model(ctx: TrialContext) -> str | None:
    override = ctx.settings.get("cli_model")
    if override:
        return str(override)
    for fam in ("opus", "sonnet", "haiku"):
        if fam in ctx.model.lower():
            return fam
    return None  # let the CLI pick its default


def _read_memory(d) -> dict[str, str]:
    return {str(p.relative_to(d)): p.read_text(errors="replace") for p in sorted(d.rglob("*.md"))} if d.exists() else {}


class ClaudeCodeAdapter(HarnessAdapter):
    name = "claude-code"
    version = "0.1.0"
    capabilities = {"tools", "max_steps", "skills", "memory"}

    def prepare(self, ctx: TrialContext) -> None:
        if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") and not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN is not set (run `claude setup-token`, put it in .env)")
        ctx.home.mkdir(parents=True, exist_ok=True)
        # Auto-memory lives in a fixed folder inside the trial home (not keyed by the workspace path),
        # so "carry" mode finds the previous trial's MEMORY.md.
        self.memory_dir = ctx.home / "memory"
        self.memory_dir.mkdir(exist_ok=True)
        (ctx.home / "settings.json").write_text(json.dumps({"autoMemoryDirectory": str(self.memory_dir)}))
        if ctx.memory_mode == "off":
            shutil.rmtree(self.memory_dir, ignore_errors=True)
            self.memory_dir.mkdir()
        self.memory_before = _read_memory(self.memory_dir)
        for s in [s.split("@")[0] for s in ctx.settings.get("skills") or []]:
            src = ctx.skills_dir / s if ctx.skills_dir else None
            if src and src.exists():
                shutil.copytree(src, ctx.workspace / ".claude" / "skills" / s, dirs_exist_ok=True)

    def run(self, ctx: TrialContext, sink: EventSink) -> RunResult:
        result = RunResult()
        cmd = ["claude", "-p", ctx.prompt, "--output-format", "stream-json", "--verbose",
               "--max-turns", str(ctx.max_steps), "--allowedTools", TOOLS]
        model = _cli_model(ctx)
        if model:
            cmd += ["--model", model]
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(ctx.home), "DISABLE_AUTOUPDATER": "1",
               "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        if ctx.memory_mode == "off":
            env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        for k in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_KEY"):
            env.pop(k, None)
        (ctx.trial_dir / "native").mkdir(exist_ok=True)
        timeout = max(1.0, ctx.deadline - time.time()) if ctx.deadline else None
        stderr = ""
        try:
            p = subprocess.run(cmd, cwd=ctx.workspace, env=env, capture_output=True, text=True, timeout=timeout)
            stdout, stderr = p.stdout, p.stderr
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            result.stop_reason = "timeout"
        (ctx.trial_dir / "native" / "claude_stream.jsonl").write_text(stdout)

        if self.memory_before and ctx.memory_mode != "off":
            # Claude Code loads MEMORY.md into the context at startup (no tool call), so record it as a read.
            sink.emit("memory_read", {"store": "MEMORY.md", "source": "auto_loaded", "files": sorted(self.memory_before)})

        final = None
        call_seq: dict[str, int] = {}
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if kind == "assistant":
                result.steps += 1
                blocks = (ev.get("message") or {}).get("content") or []
                text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                calls = [{"name": b.get("name"), "arguments": b.get("input")} for b in blocks if b.get("type") == "tool_use"]
                seq = sink.emit("llm_call", {"step": result.steps, "response": {"content": text, "tool_calls": calls}})
                if text:
                    sink.emit("agent_message", {"role": "assistant", "content": text}, parent_seq=seq)
                for b in blocks:
                    if b.get("type") == "tool_use":
                        name = b.get("name", "")
                        call_seq[b.get("id", "")] = sink.emit("tool_call", {"tool": name, "arguments": b.get("input")}, parent_seq=seq)
                        if name == "Skill":
                            sink.emit("skill_invoked", {"tool": name, "arguments": b.get("input")}, parent_seq=seq)
            elif kind == "user":
                for b in (ev.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        c = b.get("content")
                        if isinstance(c, list):
                            c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                        sink.emit("tool_result", {"tool": None, "output": str(c)[:16000], "error": bool(b.get("is_error"))},
                                  parent_seq=call_seq.get(b.get("tool_use_id", "")))
            elif kind == "result":
                final = ev

        if final:
            result.final_answer = str(final.get("result") or "").strip()
            usage = final.get("usage") or {}
            result.tokens_in = (int(usage.get("input_tokens") or 0) + int(usage.get("cache_read_input_tokens") or 0)
                                + int(usage.get("cache_creation_input_tokens") or 0))
            result.tokens_out = int(usage.get("output_tokens") or 0)
            result.steps = int(final.get("num_turns") or result.steps)
            sub = final.get("subtype", "")
            if sub == "error_max_turns":
                result.stop_reason = "step_budget"
            elif final.get("is_error"):
                result.stop_reason, result.error = "harness_error", f"{sub}: {result.final_answer}"[:2000]
        elif result.stop_reason != "timeout":
            result.stop_reason = "harness_error"
            result.error = f"claude exited without a result event: {stderr.strip()[-1500:] or stdout[-500:]}"
            sink.emit("harness_note", {"error": result.error})
        after = _read_memory(self.memory_dir)
        for k in sorted(set(after) | set(self.memory_before)):
            if after.get(k) != self.memory_before.get(k):
                sink.emit("memory_write", {"store": k, "source": "file_diff", "after": after.get(k)})
        return result

    def collect(self, ctx: TrialContext) -> dict:
        return {"memory_after": _read_memory(self.memory_dir)}
