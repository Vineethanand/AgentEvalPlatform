# Harness images

One image per harness. Workers start a fresh container from it for every trial. Each image contains
the harness itself plus `evalworker.adapters` (the adapter code that drives it).

Build from the repo root:

```bash
docker compose --profile build build harness-baseline harness-hermes
# or individually
docker build -f harnesses/baseline/Dockerfile -t aep/harness-baseline .
docker build -f harnesses/hermes/Dockerfile --build-arg HERMES_REF=<commit> -t aep/harness-hermes .
```

| Harness | Image | Notes |
| --- | --- | --- |
| `baseline` | `aep/harness-baseline` | Our transparent tool-calling loop; stdlib only. The control for harness comparisons. |
| `hermes` | `aep/harness-hermes` | [Hermes Agent](https://github.com/NousResearch/hermes-agent). Pin `HERMES_REF` to a commit so results are reproducible. |

Before trusting Hermes results, run one trial with `KEEP_TRIAL_FILES=1` and check
`data/trials/<id>/attempt-1/native/` and the trace: confirm model calls go through the gateway, and that
memory reads/writes appear (memory carry) or don't (memory off). The adapter's assumptions about Hermes's
Python API are listed at the top of `workers/evalworker/adapters/hermes.py`.
