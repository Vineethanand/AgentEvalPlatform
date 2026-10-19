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

# Every tool the CLI could use, switched off so the judge can only answer (it must not read files or browse).
NO_TOOLS = "Read,Write,Edit,Glob,Grep,Bash,WebFetch,WebSearch,Task"
TIMEOUT_S = 180


class CliJudgeError(Exception):
    """The CLI judge could not produce an answer (missing token or binary, timeout, CLI error, bad output)."""


def _command(prompt: str, model: str) -> list[str]:
    """The argv for a one-turn, tool-less, JSON-output run of the CLI."""
    return ["claude", "-p", prompt, "--output-format", "json", "--model", model,
            "--max-turns", "1", "--disallowedTools", NO_TOOLS]


def _run_docker(cmd: list[str], token: str) -> str:
    """Run the command in a fresh claude-code container and return its stdout. The container is always removed."""
    import docker  # pylint: disable=import-outside-toplevel  # only needed in docker mode

    from ..sandbox import IMAGES  # pylint: disable=import-outside-toplevel

    client = docker.from_env()
    container = None
    try:
        container = client.containers.run(
            IMAGES["claude-code"], command=cmd, entrypoint=[],
            network=os.environ.get("SANDBOX_NETWORK_CLAUDE_CODE", "aep_egress"),
            mem_limit="1g", nano_cpus=1_000_000_000, detach=True,
            environment={"CLAUDE_CODE_OAUTH_TOKEN": token, "DISABLE_AUTOUPDATER": "1",
                         "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "CLAUDE_CONFIG_DIR": "/tmp/claude-judge"},
        )
        try:
            container.wait(timeout=TIMEOUT_S)
        except Exception as e:  # pylint: disable=broad-exception-caught  # requests' ReadTimeout on wait()
            container.kill()
            raise CliJudgeError("claude CLI judge timed out") from e
        return container.logs(stdout=True, stderr=False).decode(errors="replace")
    except docker.errors.DockerException as e:
        raise CliJudgeError(f"docker error: {e}") from e
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort cleanup
                pass


def _run_local(cmd: list[str], token: str) -> str:
    """Run the command with the `claude` binary on PATH, in an empty temp folder, and return its stdout."""
    if not shutil.which("claude"):
        raise CliJudgeError("`claude` CLI not found on PATH (install Claude Code, or use SANDBOX_MODE=docker)")
    env = {**os.environ, "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    for k in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_KEY"):  # must reach Anthropic directly
        env.pop(k, None)
    with tempfile.TemporaryDirectory() as empty:
        try:
            p = subprocess.run(cmd, cwd=empty, env=env, capture_output=True, text=True, timeout=TIMEOUT_S,
                               check=False)
        except subprocess.TimeoutExpired as e:
            raise CliJudgeError("claude CLI judge timed out") from e
    return p.stdout


def ask(prompt: str, model: str = "haiku") -> tuple[str, dict]:
    """Send ``prompt`` to the CLI and return (reply text, usage with prompt_tokens / completion_tokens).

    The CLI prints a single JSON object (``--output-format json``) whose last line holds the reply in
    ``result`` and the token counts in ``usage``. Prompt tokens include cache reads and writes. Raises
    :class:`CliJudgeError` for any failure, which the judge treats like a bad reply and retries.
    """
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
