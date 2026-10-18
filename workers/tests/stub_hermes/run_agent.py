"""Stand-in for Hermes's run_agent.AIAgent, used only to test the adapter's plumbing."""
import json
import os
from pathlib import Path


class AIAgent:
    def __init__(self, base_url=None, api_key=None, model=None, max_iterations=10, quiet_mode=False,
                 disabled_toolsets=None, save_trajectories=False):
        self.disabled = disabled_toolsets or []

    def run_conversation(self, user_message):
        Path("report.json").write_text(json.dumps({"East": 32.5, "North": 159.97, "South": 298.4, "West": 56.0}))
        if "memory" not in self.disabled:
            Path(os.environ["HERMES_HOME"], "MEMORY.md").write_text("user likes json reports\n")
        return {"final_response": "done", "messages": [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "x1", "function": {"name": "write_file", "arguments": "{\"path\": \"report.json\"}"}}]},
            {"role": "tool", "tool_call_id": "x1", "name": "write_file", "content": "ok"},
            {"role": "assistant", "content": "done"},
        ]}
