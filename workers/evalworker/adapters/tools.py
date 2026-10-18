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
    p = (ws / rel).resolve()
    if ws.resolve() not in p.parents and p != ws.resolve():
        raise ValueError(f"path {rel!r} is outside the workspace")
    return p


def _trim(s: str) -> str:
    return s if len(s) <= MAX_OUTPUT else s[:MAX_OUTPUT] + f"\n...[truncated {len(s) - MAX_OUTPUT} chars]"


def schema(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props, "required": required},
    }}


class Toolbox:
    """Builds the tool list for one trial from the config's enabled tools + memory + skills."""

    def __init__(self, workspace: Path, home: Path, enabled: list[str], memory: bool, skills: list[str]):
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
                                  {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]), self.write_file),
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
        """Returns (output, is_error, args_valid)."""
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
        except Exception as e:  # tool errors go back to the model, they don't crash the run
            return f"error: {e}", True, True

    # --- tools ----------------------------------------------------------
    def bash(self, a: dict) -> str:
        try:
            p = subprocess.run(a["command"], shell=True, cwd=self.ws, capture_output=True, text=True, timeout=60)
            return f"exit={p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        except subprocess.TimeoutExpired:
            return "error: command timed out after 60s"

    def read_file(self, a: dict) -> str:
        return _safe(self.ws, a["path"]).read_text(encoding="utf-8", errors="replace")

    def write_file(self, a: dict) -> str:
        p = _safe(self.ws, a["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["content"], encoding="utf-8")
        return f"wrote {len(a['content'])} chars to {a['path']}"

    def list_dir(self, a: dict) -> str:
        p = _safe(self.ws, a.get("path") or ".")
        return "\n".join(sorted((x.name + ("/" if x.is_dir() else "")) for x in p.iterdir())) or "(empty)"

    @property
    def notes_file(self) -> Path:
        return self.home / "notes.json"

    def notes_read(self, a: dict) -> str:
        return self.notes_file.read_text() if self.notes_file.exists() else "{}"

    def notes_write(self, a: dict) -> str:
        notes = json.loads(self.notes_file.read_text()) if self.notes_file.exists() else {}
        notes[a["key"]] = a["value"]
        self.notes_file.write_text(json.dumps(notes, indent=2))
        return "saved"

    def list_skills(self, a: dict) -> str:
        return "\n".join(self.skills)

    def read_skill(self, a: dict) -> str:
        name = a["name"]
        if name not in self.skills:
            raise ValueError(f"no skill named {name!r}")
        return (self.home / "skills" / name / "SKILL.md").read_text()
