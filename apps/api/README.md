# API (NestJS)

The control plane. Owns all state and all decisions; never calls a model itself.

```bash
npm install
npm run start:dev      # needs Postgres + Redis (docker compose up postgres redis)
npm test               # statistics tests
```

Environment: `DATABASE_URL`, `REDIS_URL`, `TASKS_DIR` (default `../../tasks`), `MODELS_FILE`
(default `../../gateway/litellm_config.yaml`), `INTERNAL_TOKEN`.

## Files

| File | What it does |
| --- | --- |
| `src/entities.ts` | Data model: task, task_version, config, config_version, experiment, trial, trace_event, grade |
| `src/tasks.ts` | `POST /tasks/sync` scans `tasks/` and creates a new version when a task's content hash changes |
| `src/configs.ts` | Configs and immutable config versions; rejects settings a harness can't honour |
| `src/experiments.ts` | Expands tasks × configs × N into trials, enqueues jobs, resume/cancel, comparison, export |
| `src/trials.ts` | Trial view for the UI, and the internal endpoints workers call (spec, start, events, complete) |
| `src/stats.ts` | Paired bootstrap CI, McNemar, Fisher exact, verdict. Pure functions |
| `src/common.ts` | Hashing, harness registry, model registry loader, internal-token guard |

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/tasks/sync` | Re-scan the tasks folder |
| GET | `/tasks`, `/tasks/:id/versions` | List tasks and their versions |
| GET | `/harnesses`, `/models` | What can be configured |
| GET/POST | `/configs` | List / create a config (creates version 1) |
| POST | `/configs/:id/versions` | New version of a config |
| POST | `/experiments` | `{name, hypothesis, configVersionIds:[A,B], nTrials, nOverrides?, taskIds?, seed?}` |
| GET | `/experiments`, `/experiments/:id` | List with progress / detail with all trials |
| GET | `/experiments/:id/comparison?a=&b=&tag=&excludeTag=` | Verdict, Δ, 95% CI, McNemar, per-task, cost, failures |
| GET | `/experiments/:id/export?format=csv\|json` | Trial-level CSV, or a full JSON bundle |
| POST | `/experiments/:id/resume`, `/cancel` | Re-queue failed cells / stop queued ones |
| GET | `/trials/:id`, `/trials/:id/pair`, `/trials/:id/events` | Trial detail, same-index trial of the other config, events |
| * | `/internal/trials/:id/...` | Worker-only (header `x-internal-token`) |

## Statistics in one paragraph

Primary metric: pass rate. The headline is B − A with every task weighted equally. The 95% confidence
interval comes from a paired bootstrap that resamples tasks first (keeping A and B together) and then
trials within each task. If the interval is entirely above 0, B is better; entirely below, A is better;
otherwise "no clear difference". McNemar on one majority outcome per task is a cross-check.
