# Agent Evals Platform

Evaluate **any agent harness X with any model Y** on a set of tasks, run each task many times,
grade every run automatically, and get a statistically honest answer to *"is config B better
than config A, by how much, at what cost?"*

```
Vue UI ──► NestJS API ──► PostgreSQL
               │
               ▼ enqueue trials
        Redis + BullMQ ──► Python workers ──► one sandbox container per trial
                                │                    │ (harness adapter: Hermes / baseline)
                                ▼                    ▼
                             graders        LiteLLM gateway ──► Anthropic / OpenAI / OpenRouter
```

| Folder | What it is |
| --- | --- |
| [`apps/api`](apps/api/README.md) | NestJS control plane: tasks, configs, experiments, trials, statistics, export |
| [`apps/ui`](apps/ui/README.md) | Vue 3 screens: configs, new experiment, comparison, trial timeline |
| [`workers`](workers/README.md) | Python worker: sandbox runner, harness adapters, graders, failure rules |
| [`harnesses`](harnesses/README.md) | Docker images for each harness (baseline loop, Hermes Agent) |
| [`gateway`](gateway/litellm_config.yaml) | LiteLLM model registry: the one place models are defined |
| [`tasks`](tasks/README.md) | Task set: prompt, fixtures, grader, reference and known-bad solutions |
| [`scripts`](scripts) | Task/grader validation and experiment launcher |
| [`docs`](docs/README.md) | Design document link and experiment report template |

## Quick start (Docker)

Requirements: Docker Desktop (Windows/macOS) or Docker Engine + Compose (Linux), and at least
one model provider key.

```bash
cp .env.example .env              # then put your API key(s) in .env
docker compose --profile build build harness-baseline harness-hermes   # build the harness images
docker compose up --build         # postgres, redis, gateway, api, ui, worker
```

- UI: http://localhost:5173
- API: http://localhost:3000 (e.g. `GET /tasks`, `GET /models`)
- Gateway: http://localhost:4000

Then launch an experiment, either from the UI (**Configs** → **New experiment**) or the script:

```bash
pip install requests
# small pilot first: measures variance and token use cheaply
python scripts/run_experiment.py memory --harness baseline --model gpt-mini --n 3 --name pilot
# the real run: Hermes, memory off vs carry, same model
python scripts/run_experiment.py memory --harness hermes --model claude-sonnet --n 10
# or compare two models in one harness
python scripts/run_experiment.py models --harness hermes --model claude-sonnet --model-b qwen-open --n 10
```

More workers = faster runs: `docker compose up --scale worker=4`.

### Windows notes

- Run the commands in PowerShell from the repo folder; `cp` works in PowerShell, or use `copy .env.example .env`.
- Docker Desktop must use the WSL 2 backend. The worker starts sandbox containers through the Docker socket,
  which Docker Desktop exposes to containers at `/var/run/docker.sock`.
- If the repo is inside OneDrive, pause syncing while building, or move it out of OneDrive: file locks
  from syncing can break Docker builds and `node_modules`.

## Running without Docker (development)

```bash
# 1. infrastructure only
docker compose up postgres redis gateway

# 2. API
cd apps/api && npm install && npm run start:dev           # :3000

# 3. UI
cd apps/ui && npm install && npm run dev                  # :5173

# 4. worker, running harnesses as local subprocesses (no container isolation)
cd workers && python -m venv .venv && .venv/Scripts/activate   # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
set SANDBOX_MODE=local                      # PowerShell: $env:SANDBOX_MODE="local"
set INTERNAL_TOKEN=change-me-too            # same as in .env
set LITELLM_MASTER_KEY=sk-change-me
set TASKS_DIR=..\tasks
python -m evalworker.main
```

Local mode needs the harness importable on the host: the baseline needs nothing extra; for Hermes,
install it and set `HARNESS_PYTHONPATH` to the Hermes checkout.

## Tests

```bash
cd workers && python -m pytest -q          # worker end-to-end tests with a fake model (no keys, no Docker)
python scripts/validate_tasks.py           # every grader: reference must pass, negatives must fail
cd apps/api && npm install && npm test     # statistics: bootstrap, McNemar, Fisher, A/A false-positive rate
```

## How a trial runs

1. `POST /experiments` freezes task versions + config versions and expands **tasks × configs × N** trials.
   Trial *i* of A and B share a seed, so they are compared as a pair.
2. Jobs go on the queue interleaved (trial index outer, configs inner), so provider slowdowns hit both configs equally.
   A memory chain (teach → use) is one job, so memory can carry from one task to the next.
3. A worker copies the task fixtures into a fresh workspace, mints a per-trial gateway key with a dollar budget,
   and starts the harness in a new container on a network that can only reach the gateway.
4. The harness adapter runs the task and writes normalised trace events (`llm_call`, `tool_call`, `tool_result`,
   `memory_read`, `memory_write`, `skill_invoked`, ...).
5. The worker grades the final workspace/answer, reads tokens and cost from the gateway, assigns a failure category,
   and posts everything to the API. Posting is idempotent per attempt.
6. The comparison page shows the verdict (B better / A better / no clear difference), the difference with a 95%
   bootstrap confidence interval, a McNemar cross-check, per-task results, cost, and failure categories.

Infrastructure failures are excluded from both sides of a pair and reported; if more than 5% of trials hit them,
the verdict is withheld until you `POST /experiments/:id/resume`.

## Extending

| To add | Do this | Platform core changes |
| --- | --- | --- |
| A model | Add an entry to `gateway/litellm_config.yaml` (+ its key in `.env`) | none |
| A task | Add `tasks/<id>/` with `task.yaml`, `fixtures/`, a grader, `reference/` and `negatives/`; run `scripts/validate_tasks.py` | none |
| A harness | Write `workers/evalworker/adapters/<name>.py` (prepare / run / collect), register it in `adapters/__init__.py`, add `harnesses/<name>/Dockerfile`, add it to `HARNESSES` in `apps/api/src/common.ts` | none |
| A grader type | Write a function in `workers/evalworker/graders/` and add it to `GRADERS` | none |

## Status and known gaps

Verified in this repo:
- Worker pipeline end to end with a scripted fake model: baseline harness, local sandbox, graders, failure rules,
  memory carry vs off on a teach → use chain, and no memory leaking between independent trials.
- All deterministic graders against their reference and known-bad solutions.
- Statistics against scipy reference values, plus an A/A simulation (false "better" rate ≈ 2%).

Not yet verified (needs a machine with Docker and API keys):
- The Hermes adapter against a real Hermes install. Its assumptions are listed at the top of
  `workers/evalworker/adapters/hermes.py`; it was tested only against a stand-in `run_agent` module.
- LiteLLM per-trial keys and `/spend/logs` (the worker falls back to harness-reported tokens if this fails).
- Docker sandbox mode and the full `docker compose` stack.
- The LLM judge's agreement with human labels (see `docs/README.md` for the calibration procedure).

Simplifications versus the design document:
- Graders run in the worker process, not a separate container.
- Trace events are posted after the trial finishes rather than streamed.
- Sandboxes mount the shared trials volume, so a sandbox could in principle read other trials' folders.
- 10 scored tasks (+2 unscored teach tasks), not 24. The task format makes adding more a matter of adding folders.
- Tables are created by TypeORM `synchronize`; production use would need migrations.
