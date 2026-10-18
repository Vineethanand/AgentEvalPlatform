"""Baseline harness: a plain, fully transparent tool-calling loop.

system prompt -> call model -> run tool calls -> repeat, until the model answers
without calling a tool or a budget runs out. Because we wrote every line, any
difference between this and Hermes is attributable to Hermes.
"""
from __future__ import annotations

import json
import shutil
import time

from .base import EventSink, HarnessAdapter, RunResult, TrialContext
from .llm import LLMError, chat
from .tools import Toolbox

SYSTEM = """You are an autonomous agent working in a sandboxed workspace.
Use the tools to complete the task. Inspect files before changing them.
When you are finished, reply with your final answer and do not call any more tools.
If the task cannot be answered from the information available, say exactly: cannot determine."""

MEMORY_HINT = """You have persistent notes that survive between sessions (notes_read, notes_write).
Read them at the start of a task. Save anything you learn that would help with future tasks."""

SKILLS_HINT = "Skills with instructions for specific jobs are available (list_skills, read_skill). Check them when relevant."


class BaselineAdapter(HarnessAdapter):
    name = "baseline"
    version = "0.1.0"
    capabilities = {"tools", "temperature", "max_steps", "memory", "skills"}

    def prepare(self, ctx: TrialContext) -> None:
        ctx.home.mkdir(parents=True, exist_ok=True)
        if ctx.memory_mode == "off":
            (ctx.home / "notes.json").unlink(missing_ok=True)
        skills = [s.split("@")[0] for s in ctx.settings.get("skills") or []]
        for s in skills:
            src = ctx.skills_dir / s if ctx.skills_dir else None
            if src and src.exists():
                shutil.copytree(src, ctx.home / "skills" / s, dirs_exist_ok=True)
        self.toolbox = Toolbox(
            ctx.workspace, ctx.home,
            enabled=ctx.settings.get("tools") or ["bash", "read_file", "write_file", "list_dir"],
            memory=ctx.memory_mode != "off",
            skills=skills,
        )

    def run(self, ctx: TrialContext, sink: EventSink) -> RunResult:
        system = ctx.settings.get("system_prompt_override") or SYSTEM
        if ctx.memory_mode != "off":
            system += "\n\n" + MEMORY_HINT
        if self.toolbox.skills:
            system += "\n\n" + SKILLS_HINT
        messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": ctx.prompt}]
        result = RunResult()
        token_budget = int(ctx.settings.get("max_tokens_total", 200_000))

        while True:
            if result.steps >= ctx.max_steps:
                result.stop_reason = "step_budget"
                break
            if self.out_of_time(ctx):
                result.stop_reason = "timeout"
                break
            if result.tokens_in + result.tokens_out >= token_budget:
                result.stop_reason = "token_budget"
                break

            t0 = time.time()
            try:
                resp = chat(ctx.gateway_url, ctx.api_key, ctx.model, messages, self.toolbox.schemas,
                            temperature=ctx.temperature, seed=ctx.seed)
            except LLMError as e:
                result.stop_reason = "harness_error"
                result.error = str(e)
                sink.emit("harness_note", {"error": str(e)})
                break
            result.steps += 1
            usage = resp.get("usage") or {}
            result.tokens_in += int(usage.get("prompt_tokens") or 0)
            result.tokens_out += int(usage.get("completion_tokens") or 0)
            msg = (resp.get("choices") or [{}])[0].get("message") or {}
            call_seq = sink.emit("llm_call", {
                "model": ctx.model, "step": result.steps,
                "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                "latency_ms": int((time.time() - t0) * 1000),
                "response": {"content": msg.get("content"), "tool_calls": msg.get("tool_calls")},
            })
            if msg.get("content"):
                sink.emit("agent_message", {"role": "assistant", "content": msg["content"]}, parent_seq=call_seq)

            tool_calls = msg.get("tool_calls") or []
            messages.append({"role": "assistant", "content": msg.get("content"), **({"tool_calls": tool_calls} if tool_calls else {})})
            if not tool_calls:
                result.final_answer = (msg.get("content") or "").strip()
                break

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name, raw = fn.get("name", ""), fn.get("arguments", "{}")
                tseq = sink.emit("tool_call", {"tool": name, "arguments": raw}, parent_seq=call_seq)
                out, is_err, valid = self.toolbox.call(name, raw)
                if not valid:
                    sink.emit("harness_note", {"invalid_tool_call": name, "arguments": raw}, parent_seq=tseq)
                sink.emit("tool_result", {"tool": name, "output": out, "error": is_err, "schema_valid": valid}, parent_seq=tseq)
                if name == "notes_read":
                    sink.emit("memory_read", {"store": "notes.json", "content": out}, parent_seq=tseq)
                elif name == "notes_write" and not is_err:
                    sink.emit("memory_write", {"store": "notes.json", "arguments": raw}, parent_seq=tseq)
                elif name == "read_skill" and not is_err:
                    sink.emit("skill_invoked", {"skill": json.loads(raw).get("name")}, parent_seq=tseq)
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": out})

        (ctx.trial_dir / "native").mkdir(exist_ok=True)
        (ctx.trial_dir / "native" / "messages.json").write_text(json.dumps(messages, indent=2, default=str))
        return result

    def collect(self, ctx: TrialContext) -> dict:
        f = ctx.home / "notes.json"
        return {"memory_after": f.read_text() if f.exists() else None}
