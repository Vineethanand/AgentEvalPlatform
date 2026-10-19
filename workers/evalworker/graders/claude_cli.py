"""Run one judge prompt through the `claude` CLI (Claude Code, Haiku by default) instead of the gateway.

Like the claude-code harness it authenticates with CLAUDE_CODE_OAUTH_TOKEN and talks to Anthropic directly.
- SANDBOX_MODE=docker: a throwaway container from the claude-code harness image on the egress network, with
  no mounts, so the judge sees only the prompt.
- SANDBOX_MODE=local: the `claude` binary on the worker's PATH, run in an empty temp folder.
The CLI is given no tools and one turn: it only has to answer with the rubric JSON.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

NO_TOOLS = "Read,Write,Edit,Glob,Grep,Bash,WebFetch,WebSearch,Task"
TIMEOUT_S = 180


class CliJudgeError(Exception):
    pass


def _command(prompt: str, model: str) -> list[str]:
    return ["claude", "-p", prompt, "--output-format", "json", "--model", model,
            "--max-turns", "1", "--disallowedTools", NO_TOOLS]


def _run_docker(cmd: list[str], token: str) -> str:
    import docker

    from ..sandbox import IMAGES

    client = docker.from_env()
    container = None
    try:
        container = client.containers.run(
            IMAGES["claude-code"], command=cmd, entrypoint=[], network=os.environ.get("SANDBOX_NETWORK_CLAUDE_CODE", "aep_egress"),
            mem_limit="1g", nano_cpus=1_000_000_000, detach=True,
            environment={"CLAUDE_CODE_OAUTH_TOKEN": token, "DISABLE_AUTOUPDATER": "1",
                         "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "CLAUDE_CONFIG_DIR": "/tmp/claude-judge"},
        )
        try:
            container.wait(timeout=TIMEOUT_S)
        except Exception:  # noqa: BLE001 - requests ReadTimeout
            container.kill()
            raise CliJudgeError("claude CLI judge timed out")
        return container.logs(stdout=True, stderr=False).decode(errors="replace")
    except docker.errors.DockerException as e:
        raise CliJudgeError(f"docker error: {e}") from e
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:  # noqa: BLE001
                pass


def _run_local(cmd: list[str], token: str) -> str:
    if not shutil.which("claude"):
        raise CliJudgeError("`claude` CLI not found on PATH (install Claude Code, or use SANDBOX_MODE=docker)")
    env = {**os.environ, "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    for k in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_KEY"):
        env.pop(k, None)
    with tempfile.TemporaryDirectory() as empty:
        try:
            p = subprocess.run(cmd, cwd=empty, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as e:
            raise CliJudgeError("claude CLI judge timed out") from e
    return p.stdout


def ask(prompt: str, model: str = "haiku") -> tuple[str, dict]:
    """Return (reply text, usage dict with prompt_tokens/completion_tokens)."""
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if not token and not os.environ.get("ANTHROPIC_API_KEY"):
        raise CliJudgeError("CLAUDE_CODE_OAUTH_TOKEN is not set (run `claude setup-token`, put it in .env)")
    cmd = _command(prompt, model)
    out = _run_docker(cmd, token) if os.environ.get("SANDBOX_MODE", "local") == "docker" else _run_local(cmd, token)
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as e:
        raise CliJudgeError(f"claude CLI returned no JSON result: {out[-300:]!r}") from e
    if data.get("is_error"):
        raise CliJudgeError(f"claude CLI error: {str(data.get('result'))[:300]}")
    u = data.get("usage") or {}
    return str(data.get("result") or ""), {
        "prompt_tokens": int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
        + int(u.get("cache_creation_input_tokens") or 0),
        "completion_tokens": int(u.get("output_tokens") or 0)}
