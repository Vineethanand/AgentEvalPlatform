"""Stand-in for Hermes's run_agent.AIAgent, used only to test the adapter's plumbing."""
import json
import os
from pathlib import Path


class AIAgent:  # pylint: disable=too-few-public-methods
    """Accepts the constructor arguments the real AIAgent does (but not ``temperature``, like the installed one).

    Only ``disabled_toolsets`` has an effect: it decides whether the stub writes a memory file.
    """

    def __init__(self, **kwargs):
        """Remember which toolsets are disabled; every other argument is accepted and ignored."""
        self.disabled = kwargs.get("disabled_toolsets") or []

    def run_conversation(self, user_message):
        """Pretend to solve the csv-aggregate task: write the report file, maybe write memory, return messages."""
        report = {"East": 32.5, "North": 159.97, "South": 298.4, "West": 56.0}
        Path("report.json").write_text(json.dumps(report), encoding="utf-8")
        if "memory" not in self.disabled:
            Path(os.environ["HERMES_HOME"], "MEMORY.md").write_text("user likes json reports\n", encoding="utf-8")
        return {"final_response": json.dumps(report), "messages": [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "x1", "function": {"name": "write_file", "arguments": "{\"path\": \"report.json\"}"}}]},
            {"role": "tool", "tool_call_id": "x1", "name": "write_file", "content": "ok"},
            {"role": "assistant", "content": json.dumps(report)},
        ]}
