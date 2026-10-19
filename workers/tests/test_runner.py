"""End-to-end worker tests: real Runner + LocalSandbox + baseline adapter + graders,
against a scripted fake model. No network, no Docker, no API needed.

Run:  cd workers && python -m pytest -q      (or: python -m unittest discover -s tests)
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import yaml

from evalworker.failure_rules import classify
from evalworker.runner import Runner
from evalworker.sandbox import LocalSandbox

from fakes import FakeApi, FakeModelServer, NoGateway, tool_call

TASKS = Path(__file__).resolve().parents[2] / "tasks"


def spec_for(task_id: str, trial_id: str, settings: dict | None = None, seed: int = 1) -> dict:
    """Build the spec the API would return for a trial of ``task_id`` on a baseline/fake-model config.

    ``settings`` overrides the default config settings (for example ``{"memory": {"mode": "carry"}}``).
    """
    task = yaml.safe_load((TASKS / task_id / "task.yaml").read_text(encoding="utf-8"))
    return {
        "trial": {"id": trial_id, "seed": seed, "attempt": 0},
        "task": task,
        "config": {
            "harness": "baseline", "modelAlias": "fake-model",
            "modelSnapshot": {"priceInputPerMtok": 1.0, "priceOutputPerMtok": 5.0},
            "settings": {"temperature": 0, "max_steps": 6, "tools": ["bash", "read_file", "write_file", "list_dir"],
                         "memory": {"mode": "off"}, **(settings or {})},
        },
    }


class RunnerTests(unittest.TestCase):
    """Whole trials through the real runner with a scripted model."""

    def setUp(self):
        """Use a temporary trials folder and keep each trial's files so tests can inspect them."""
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with  # closed in tearDown
        os.environ["KEEP_TRIAL_FILES"] = "1"

    def tearDown(self):
        """Delete the temporary trials folder."""
        self.tmp.cleanup()

    def make_runner(self, api, server):
        """A real Runner wired to the fake API, the fake model server and the in-process sandbox."""
        r = Runner(api=api, gateway=NoGateway(server.url), sandbox=LocalSandbox(),
                   trials_dir=self.tmp.name, tasks_dir=str(TASKS))
        r.sandbox_gateway = server.url
        return r

    def test_passing_trial_records_events_grade_and_cost(self):
        """A correct run passes, records its trace, and its cost is tokens x the price snapshot."""
        report = {"East": 32.5, "North": 159.97, "South": 298.4, "West": 56.0}

        def script(messages):
            if not any(m["role"] == "tool" for m in messages):
                return tool_call("write_file", {"path": "report.json", "content": json.dumps(report)})
            return {"content": json.dumps(report)}

        server = FakeModelServer(script)
        api = FakeApi({"t1": spec_for("csv-aggregate", "t1")})
        self.make_runner(api, server).run_job(["t1"])
        server.close()

        done = api.completed["t1"]
        self.assertEqual(done["status"], "done")
        self.assertTrue(done["passed"])
        self.assertIsNone(done["failureCategory"])
        self.assertEqual(done["steps"], 2)
        self.assertEqual((done["tokensIn"], done["tokensOut"]), (200, 40))
        self.assertAlmostEqual(done["costUsd"], 200 * 1e-6 + 40 * 5e-6)
        types = [e["type"] for e in api.event_log["t1"]]
        self.assertEqual(types.count("llm_call"), 2)
        self.assertIn("tool_call", types)
        self.assertIn("tool_result", types)

    def test_looping_agent_hits_budget_and_is_classified(self):
        """An agent that never stops calling tools ends at the step budget and is labelled budget_exhausted."""
        server = FakeModelServer(lambda m: tool_call("list_dir", {"path": "."}))
        api = FakeApi({"t2": spec_for("csv-aggregate", "t2")})
        self.make_runner(api, server).run_job(["t2"])
        server.close()
        done = api.completed["t2"]
        self.assertEqual(done["status"], "done")
        self.assertFalse(done["passed"])
        self.assertEqual(done["stopReason"], "step_budget")
        self.assertEqual(done["failureCategory"], "budget_exhausted")

    def _memory_chain(self, mode: str) -> dict:
        """Run the M2 teach task then the use task as one chain; return both trials' results.

        The scripted model plays an agent that can only know the check command from memory: in the teach task
        it runs the command and saves it as a note (if note tools exist); in the use task it reads its notes
        and runs the saved command, or, with no notes tool, guesses a command without the required flag.
        """

        def script(messages):  # pylint: disable=too-many-return-statements
            tool_msgs = [m for m in messages if m["role"] == "tool"]
            prompt = messages[1]["content"]
            has_notes = "persistent notes" in messages[0]["content"]
            command = "python qa/run_suite.py --suite=nightly-4"
            if "custom check suite" in prompt:  # teach task: run the command, save it if possible
                if not tool_msgs:
                    return tool_call("bash", {"command": command})
                if has_notes and len(tool_msgs) == 1:
                    return tool_call("notes_write", {"key": "checks", "value": command}, "c2")
                return {"content": "SUITE nightly-4: 4 passed, 0 failed"}
            # use task: nothing in the prompt says which command to run
            if has_notes:
                if not tool_msgs:
                    return tool_call("notes_read", {})
                if len(tool_msgs) == 1 and "nightly-4" in tool_msgs[0]["content"]:
                    return tool_call("bash", {"command": command}, "c3")
                return {"content": "done"}
            if not tool_msgs:  # without memory the agent can only guess the command
                return tool_call("bash", {"command": "python qa/run_suite.py"}, "c4")
            return {"content": "done"}

        server = FakeModelServer(script)
        s = {"memory": {"mode": mode}}
        api = FakeApi({"teach": spec_for("m2-teach-checks", "teach", s), "use": spec_for("m2-use-checks", "use", s)})
        self.make_runner(api, server).run_job(["teach", "use"])
        server.close()
        return api.completed

    def test_memory_carry_passes_use_task(self):
        """With memory carried over, the use task finds the saved command and passes."""
        done = self._memory_chain("carry")
        self.assertTrue(done["use"]["passed"], done["use"])

    def test_memory_off_fails_use_task_and_flags_ignored_memory(self):
        """With memory off, the use task fails and the failure is labelled ignored_memory."""
        done = self._memory_chain("off")
        self.assertFalse(done["use"]["passed"])
        self.assertEqual(done["use"]["failureCategory"], "ignored_memory")

    def test_memory_does_not_leak_between_independent_trials(self):
        """Two separate jobs with memory 'fresh': the second must not see the first's notes."""
        seen = []

        def script(messages):
            tool_msgs = [m for m in messages if m["role"] == "tool"]
            if not tool_msgs:
                return tool_call("notes_read", {})
            if len(tool_msgs) == 1:
                seen.append(tool_msgs[0]["content"])
                return tool_call("notes_write", {"key": "secret", "value": "from-first-trial"}, "c2")
            return {"content": "ok"}

        server = FakeModelServer(script)
        s = {"memory": {"mode": "fresh"}}
        api = FakeApi({"a": spec_for("log-triage", "a", s), "b": spec_for("log-triage", "b", s)})
        r = self.make_runner(api, server)
        r.run_job(["a"])
        r.run_job(["b"])
        server.close()
        self.assertEqual(seen, ["{}", "{}"])


class FailureRuleTests(unittest.TestCase):
    """The failure-category rules on hand-made traces."""

    @staticmethod
    def ev(tool, args):
        """A tool_call trace event."""
        return {"type": "tool_call", "payload": {"tool": tool, "arguments": args}}

    def test_loop(self):
        """The same call three times in a row is a loop."""
        events = [self.ev("bash", "ls")] * 3
        self.assertEqual(classify(status="done", stop_reason="completed", passed=False, events=events,
                                  task={}, grades=[], max_steps=25, final_answer="x"), "loop")

    def test_passed_has_no_category(self):
        """A passing trial has no failure category."""
        self.assertIsNone(classify(status="done", stop_reason="completed", passed=True, events=[],
                                   task={}, grades=[], max_steps=25, final_answer=""))

    def test_infra(self):
        """A sandbox failure is always an infra_error, whatever else is true."""
        self.assertEqual(classify(status="infra_error", stop_reason="", passed=None, events=[],
                                  task={}, grades=[], max_steps=25, final_answer=""), "infra_error")


class HermesAdapterPlumbingTests(unittest.TestCase):
    """Uses tests/stub_hermes/run_agent.py instead of real Hermes: checks config mapping,
    event translation and memory-file diffing. Real Hermes is exercised in the harness image."""

    def run_with(self, mode):
        """Run one csv-aggregate trial through the Hermes adapter with the stub, in the given memory mode."""
        os.environ["HARNESS_PYTHONPATH"] = str(Path(__file__).parent / "stub_hermes")
        with tempfile.TemporaryDirectory() as tmp:
            spec = spec_for("csv-aggregate", "h1", {"memory": {"mode": mode}})
            spec["config"]["harness"] = "hermes"
            api = FakeApi({"h1": spec})
            r = Runner(api=api, gateway=NoGateway("http://127.0.0.1:9"), sandbox=LocalSandbox(),
                       trials_dir=tmp, tasks_dir=str(TASKS))
            r.run_job(["h1"])
        del os.environ["HARNESS_PYTHONPATH"]
        return api

    def test_events_and_grade(self):
        """The stub's run is graded, translated to two llm_call events, and its memory write is seen."""
        api = self.run_with("fresh")
        done = api.completed["h1"]
        self.assertTrue(done["passed"], done)
        types = [e["type"] for e in api.event_log["h1"]]
        self.assertEqual(types.count("llm_call"), 2)
        self.assertIn("memory_write", types)

    def test_memory_off_disables_memory_toolset(self):
        """Memory off must stop the stub from writing memory, so no memory_write event appears."""
        api = self.run_with("off")
        self.assertNotIn("memory_write", [e["type"] for e in api.event_log["h1"]])


if __name__ == "__main__":
    unittest.main()
