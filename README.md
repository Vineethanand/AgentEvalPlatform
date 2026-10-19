# Agent Evals Platform

Evaluate **any agent harness X with any model Y** on a set of tasks, run each task many times,
grade every run automatically, and get a statistically honest answer to *"is config B better
than config A, by how much, at what cost?"*

```
Vue UI ──► NestJS API ──► PostgreSQL
               │
               ▼ enqueue trials
        Redis + BullMQ ──► Python workers ──► one sandbox container per trial
                                │                    │ (harness adapter: Hermes / baseline / Claude Code)
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

### Runs so far (real models)

| Harness | Model | Result |
| --- | --- | --- |
| Claude Code | Claude Haiku, run against several tasks using the Claude Code credentials (`CLAUDE_CODE_OAUTH_TOKEN`) | Works. This path calls Anthropic directly and does not use the gateway or an API key |
| Hermes | Paid models (`claude-haiku`, `claude-sonnet`, `gpt-mini`) | **Not run.** There is no Anthropic or OpenAI API credit for the gateway, so no model that needs credits has been run through Hermes |
| Hermes | Free OpenRouter models (`laguna-xs-free`, `inkling-small-free`) | Works, but the free tier's daily request limit (50/day) was hit after only a few experiments. `inkling-small-free` is also refused by OpenRouter outside its approved agentic harnesses |
| Hermes | Local Ollama: `qwen2.5:1.5b` (`ollama-qwen-1.5b`) and `qwen2.5:3b` (`ollama-qwen-3b`), plus `qwen2.5:7b` (`ollama-qwen`) | Runs end to end through the gateway. This confirms the Hermes harness itself works; see the local-model notes below for the quality limits |

Assumption: the LLM judge can run through the Claude Code CLI with Haiku (`JUDGE_BACKEND=claude-cli`), since the
Claude Code credentials work and the gateway judge model has no API credit behind it. Judge calls on that path use the
subscription token, so their cost is not reported in the gateway spend totals.

Assumption: Claude Code credentials are available and Haiku was run through the Claude Code harness. To run Hermes with
Claude or OpenAI models you would need API credit on those accounts. Anthropic API keys also need
`anthropic-workspace-id` set on the model in `gateway/litellm_config.yaml`.

### Using local Ollama models

1. `ollama pull qwen2.5:1.5b` (and/or `qwen2.5:3b`), with `ollama serve` running on the host.
2. The aliases `ollama-qwen`, `ollama-qwen-1.5b` and `ollama-qwen-3b` are already in `gateway/litellm_config.yaml`
   and reach Ollama at `host.docker.internal:11434`. Restart the gateway after editing it:
   `docker compose restart gateway`.
3. Pick one of those aliases for a Hermes config.

Known limits of the local models (with CPU-only inference):
- Very slow: a single Hermes step on `qwen2.5:7b` took 90 to 140 seconds, so trials often hit their timeout.
- Ollama's default 4096-token context clips Hermes's prompt, so the `1.5b` and `3b` entries set `num_ctx: 16384`.
- Small Qwen models often call Hermes's `tool_call` wrapper without its required `calls` array, so the call is
  rejected. Treat them as a check that the plumbing works, not as a fair comparison against hosted models.

### Task set

Besides the existing tasks, these were added as harder, reasoning-heavy tasks (each with a reference solution and
known-bad answers that `scripts/validate_tasks.py` checks):

- **`csv-aggregate`**: aggregate functions over values, e.g. revenue per region from a CSV (quantity × unit price,
  refunded rows excluded).
- **`tile-defect`**: find the one wrong pixel in a 32×32 image made of a repeating 4×4 tile, and report its row, column
  and tile.
- **`job-schedule`**: order 20 batch jobs by finish time across different UTC offsets and report peak concurrency.

LLM judge backend: by default the judge calls a gateway alias (`JUDGE_MODEL`, `gpt-judge`), which needs OpenAI credit.
Set `JUDGE_BACKEND=claude-cli` in `.env` to judge with Claude Code Haiku instead (`JUDGE_CLI_MODEL`, default `haiku`).
A task can also pick it with `backend: claude-cli` on its `llm_judge` grader. It is a worker-wide setting rather than
a UI option, so every config in an experiment is judged by the same model. In Docker the judge runs in a throwaway
claude-code container with no mounted files; locally it needs `claude` on the PATH.

LLM-judge calibration: manual labels for `postmortem-from-logs` are in `tasks/postmortem-from-logs/labels/`, and
`scripts/calibrate_judge.py` compares the judge against them (see `docs/README.md`).

### Verified in this repo

- Worker pipeline end to end with a scripted fake model: baseline harness, local sandbox, graders, failure rules,
  memory carry vs off on a teach → use chain, and no memory leaking between independent trials.
- All deterministic graders against their reference and known-bad solutions.
- Statistics against scipy reference values, plus an A/A simulation (false "better" rate ≈ 2%).

Not yet verified:
- The Hermes adapter's assumptions about its Python API are listed at the top of
  `workers/evalworker/adapters/hermes.py`. It now runs against the real Hermes image (see the table above),
  but not every assumption has been checked; for example the installed Hermes ignores the `temperature` setting.
- Hermes with a paid model (Claude, GPT): no API credit was available.
- The LLM judge's agreement with human labels (see `docs/README.md` for the calibration procedure).

Simplifications versus the design document:
- Graders run in the worker process, not a separate container.
- Trace events are posted after the trial finishes rather than streamed.
- 21 scored tasks (+3 unscored teach tasks), covering exact_match, state_check, unit_test, trace_check and llm_judge
  graders. Several tasks only tell configs apart when a skill or memory is on (see `tasks/README.md`).

Isolation: each trial runs in its own container that mounts only that trial's folder (and, in a "carry" memory
chain, the shared memory home), not the whole trials volume. One trial cannot read or change another's files;
state carries between trials only when a memory setting says so.
- Tables are created by TypeORM `synchronize`; production use would need migrations.
