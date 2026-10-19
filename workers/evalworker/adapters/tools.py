"""Tools the baseline harness exposes to the model, as OpenAI function schemas.

All file paths are confined to the trial workspace. The sandbox container is the
real isolation boundary; this confinement just keeps the agent's view simple.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

MAX_OUTPUT = 16_000


def _safe(ws: Path, rel: str) -> Path:
    """Resolve ``rel`` inside the workspace, refusing anything that escapes it (``../x``, absolute paths).

    ``resolve()`` follows symlinks and removes ``..``, so the check compares real paths: the result must be
    the workspace itself or one of its descendants.
    """
    p = (ws / rel).resolve()
    if ws.resolve() not in p.parents and p != ws.resolve():
        raise ValueError(f"path {rel!r} is outside the workspace")
    return p


def _trim(s: str) -> str:
    """Cut tool output at MAX_OUTPUT characters (and say so) so one huge file cannot flood the model's context."""
    return s if len(s) <= MAX_OUTPUT else s[:MAX_OUTPUT] + f"\n...[truncated {len(s) - MAX_OUTPUT} chars]"


def schema(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict:
    """Build an OpenAI function-calling schema for one tool."""
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props, "required": required},
    }}


class Toolbox:
    """Builds the tool list for one trial from the config's enabled tools + memory + skills."""

    def __init__(self, workspace: Path, home: Path, enabled: list[str], memory: bool, skills: list[str]):
        """Register the enabled file/shell tools, plus note tools if memory is on and skill tools if any skill is.

        ``schemas`` is what the model sees; ``impl`` maps a tool name to the Python method that runs it.
        """
        self.ws = workspace
        self.home = home
        self.memory = memory
        self.skills = skills
        self.impl: dict[str, Callable[[dict], str]] = {}
        self.schemas: list[dict] = []
        all_tools = {
            "bash": (schema("bash", "Run a shell command in the workspace. Returns stdout, stderr and exit code.",
                            {"command": {"type": "string"}}, ["command"]), self.bash),
            "read_file": (schema("read_file", "Read a text file from the workspace.",
                                 {"path": {"type": "string"}}, ["path"]), self.read_file),
            "write_file": (schema("write_file", "Write (overwrite) a text file in the workspace.",
                                  {"path": {"type": "string"}, "content": {"type": "string"}},
                                  ["path", "content"]), self.write_file),
            "list_dir": (schema("list_dir", "List files in a workspace directory.",
                                {"path": {"type": "string"}}, []), self.list_dir),
        }
        for name in enabled:
            if name in all_tools:
                s, f = all_tools[name]
                self.schemas.append(s)
                self.impl[name] = f
        if memory:
            self.schemas += [
                schema("notes_read", "Read your persistent notes from earlier sessions.", {}, []),
                schema("notes_write", "Save a note that persists to future sessions.",
                       {"key": {"type": "string"}, "value": {"type": "string"}}, ["key", "value"]),
            ]
            self.impl["notes_read"] = self.notes_read
            self.impl["notes_write"] = self.notes_write
        if skills:
            self.schemas += [
                schema("list_skills", "List available skills (instructions for specific jobs).", {}, []),
                schema("read_skill", "Read a skill's instructions.", {"name": {"type": "string"}}, ["name"]),
            ]
            self.impl["list_skills"] = self.list_skills
            self.impl["read_skill"] = self.read_skill

    # --- dispatch -------------------------------------------------------
    def call(self, name: str, raw_args: str) -> tuple[str, bool, bool]:
        """Run tool ``name`` with the model's raw JSON arguments. Returns (output, is_error, args_valid).

        ``args_valid`` is False for an unknown tool or arguments that are not a JSON object; the harness records
        those as invalid tool calls in the trace, which is how tool-calling reliability is compared across models.
        An error raised by a tool is returned to the model as text instead of crashing the run, so it can recover.
        """
        if name not in self.impl:
            return f"error: unknown tool {name!r}", True, False
        try:
            args = json.loads(raw_args or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            return f"error: invalid arguments: {e}", True, False
        try:
            return _trim(self.impl[name](args)), False, True
        except Exception as e:  # pylint: disable=broad-exception-caught  # any tool error goes back to the model
            return f"error: {e}", True, True

    # --- tools ----------------------------------------------------------
    def bash(self, a: dict) -> str:
        """Run a shell command in the workspace (60 s limit) and return its exit code, stdout and stderr."""
        try:
            p = subprocess.run(a["command"], shell=True, cwd=self.ws, capture_output=True, text=True,
                               timeout=60, check=False)
            return f"exit={p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        except subprocess.TimeoutExpired:
            return "error: command timed out after 60s"

    def read_file(self, a: dict) -> str:
        """Return a workspace file's text (undecodable bytes are replaced rather than raising)."""
        return _safe(self.ws, a["path"]).read_text(encoding="utf-8", errors="replace")

    def write_file(self, a: dict) -> str:
        """Create or overwrite a workspace file, creating missing parent folders."""
        p = _safe(self.ws, a["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["content"], encoding="utf-8")
        return f"wrote {len(a['content'])} chars to {a['path']}"

    def list_dir(self, a: dict) -> str:
        """List a workspace folder, one name per line, with a trailing "/" on sub-folders."""
        p = _safe(self.ws, a.get("path") or ".")
        return "\n".join(sorted((x.name + ("/" if x.is_dir() else "")) for x in p.iterdir())) or "(empty)"

    @property
    def notes_file(self) -> Path:
        """The persistent notes store. It lives in ``home``, which survives between trials only in carry mode."""
        return self.home / "notes.json"

    def notes_read(self, _args: dict) -> str:
        """Return all saved notes as JSON ("{}" when there are none)."""
        return self.notes_file.read_text(encoding="utf-8") if self.notes_file.exists() else "{}"

    def notes_write(self, a: dict) -> str:
        """Save one key/value note, keeping the notes saved earlier."""
        notes = json.loads(self.notes_file.read_text(encoding="utf-8")) if self.notes_file.exists() else {}
        notes[a["key"]] = a["value"]
        self.notes_file.write_text(json.dumps(notes, indent=2), encoding="utf-8")
        return "saved"

    def list_skills(self, _args: dict) -> str:
        """Names of the skills enabled for this trial, one per line."""
        return "\n".join(self.skills)

    def read_skill(self, a: dict) -> str:
        """Return the SKILL.md of an enabled skill; only skills enabled in the config can be read."""
        name = a["name"]
        if name not in self.skills:
            raise ValueError(f"no skill named {name!r}")
        return (self.home / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
