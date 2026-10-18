# Worker (Python)

Pulls jobs from the `trials` BullMQ queue, runs each trial in a sandbox, grades it and reports back.

```bash
pip install -r requirements.txt
python -m evalworker.main          # needs API, Redis and the gateway running
python -m pytest -q                # tests: fake model server, no keys or Docker needed
```

| Env var | Default | Meaning |
| --- | --- | --- |
| `API_URL` | `http://localhost:3000` | NestJS API |
| `REDIS_URL` | `redis://localhost:6379` | Queue |
| `GATEWAY_URL` | `http://localhost:4000` | LiteLLM, as the worker reaches it |
| `SANDBOX_GATEWAY_URL` | = `GATEWAY_URL` | LiteLLM, as the sandbox reaches it |
| `LITELLM_MASTER_KEY` | | Mints per-trial keys, reads spend logs, runs the judge |
| `INTERNAL_TOKEN` | | Shared secret for the API's internal endpoints |
| `SANDBOX_MODE` | `local` | `docker` = one container per trial; `local` = subprocess |
| `TASKS_DIR` / `TRIALS_DIR` | `../tasks` / `./data/trials` | Task definitions / per-trial working folders |
| `JUDGE_MODEL` | `gpt-judge` | Gateway alias of the LLM judge |
| `KEEP_TRIAL_FILES` | | `1` keeps each trial's workspace for debugging |

## Layout

```
evalworker/
  main.py            BullMQ worker loop
  runner.py          one job = one trial or a memory chain; the full trial lifecycle
  sandbox.py         DockerSandbox (per-trial container) and LocalSandbox (subprocess)
  clients.py         API client; gateway client (per-trial keys, spend logs)
  failure_rules.py   failure taxonomy (loop, budget, wrong tool, ignored memory, ...)
  adapters/
    base.py          THE CONTRACT: TrialContext, EventSink, RunResult, HarnessAdapter
    run.py           entry point inside the sandbox
    baseline.py      our plain tool-calling loop
    hermes.py        Hermes Agent adapter
    llm.py, tools.py stdlib OpenAI-compatible client; workspace tools
  graders/
    deterministic.py exact_match, unit_test, state_check, trace_check
    llm_judge.py     rubric judge (yes/no per criterion, reason before verdict)
tests/               end-to-end tests with a scripted fake model; stub Hermes module
```

## Writing a harness adapter

```python
class MyAdapter(HarnessAdapter):
    name = "mine"
    capabilities = {"tools", "temperature", "max_steps"}

    def prepare(self, ctx):        # write native config, install skills, reset or keep memory in ctx.home
        ...
    def run(self, ctx, sink):      # point the harness at ctx.gateway_url with ctx.api_key and ctx.model
        sink.emit("llm_call", {...})   # one event per step
        return RunResult(final_answer=..., stop_reason="completed", steps=...)
    def collect(self, ctx):        # optional: memory files after the run, etc.
        return {}
```

Register it in `adapters/__init__.py`, add `harnesses/mine/Dockerfile`, and add it to `HARNESSES` in
`apps/api/src/common.ts` so configs can use it.
