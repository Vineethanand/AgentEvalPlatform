# Experiment report: baseline + Ollama Qwen vs Claude Code + Haiku (memory off)

Experiment name: `baseline-ollama-memory-off v1 vs claude-haiku-memory-off v1`. Run on 2026-10-19.

## Hypothesis (written before the run)

Recorded on the experiment: **"claude haiku will perform better."**

No hypotheses were written down for cost or for individual tasks, so this report makes none after the fact.

## Setup

| Item | Value |
| --- | --- |
| Config A | `baseline` harness, `ollama-qwen` (local `qwen2.5:7b`), memory off. Config version id: `0fe01325-11ed-47e2-8388-338aab45cc84` (v1) |
| Config B | `claude-code` harness, `claude-haiku` (`claude-haiku-4-5`), memory off. Config version id: `f07a5722-2d47-486d-880a-198fcaedefe8` (v1) |
| Same in both | Settings as stored: temperature 0.7, max 25 steps, 600 s timeout, 200,000 max tokens, no skills, same seeds (seed 1234). The `claude-code` harness does not list `temperature` among its capabilities, so that setting may not have applied to B |
| Different | Harness **and** model differ (see Caveats) |
| Tasks | 2 scored: `csv-aggregate`, `config-migrate` |
| Trials | N = 7 per task per config, so 14 per config and 14 pairs |
| Hermes commit | Not applicable: Hermes was not used |
| Experiment id | `c5578f0c-143d-4f3b-bdf2-268d23a25702` |

## Results

From `GET /experiments/c5578f0c-143d-4f3b-bdf2-268d23a25702/comparison`. The memory-task rows from the template do not
apply: neither task uses memory, and memory is off in both configs.

| Metric | A: baseline + Qwen 7B | B: Claude Code + Haiku | B − A | 95% CI | Verdict |
| --- | --- | --- | --- | --- | --- |
| Pass rate, all tasks | 50% (7 of 14) | 100% (14 of 14) | +50 points | 14 to 86 points | B better (bootstrap p = 0.0076) |
| Cost per trial (USD) | 0 (local model) | 0.0438 | +0.0438 | 0.0371 to 0.0530 | |
| Tokens per trial | 985 | 42,064 | +41,078 | 34,718 to 49,910 | |
| Median latency | 45.1 s | 7.8 s | | | |

Per task:

| Task | A passes | B passes | B − A | p | Label |
| --- | --- | --- | --- | --- | --- |
| `csv-aggregate` | 2 of 7 | 7 of 7 | +71 points | 0.021 | significant |
| `config-migrate` | 5 of 7 | 7 of 7 | +29 points | 0.46 | noise |

Failure categories for A: `wrong_answer` 6, `gave_up_early` 1. B had none. Infrastructure failures: 0 on both sides.

McNemar (all tasks): only A 0, only B 1, both pass 1, neither 0, p = 1. This test counted only the 2 tasks as pairs, so
it carries almost no information here. The bootstrap result over the 14 trial pairs is the one to rely on.

## Cost

Formula: tasks × trials × configs × average tokens per trial × price per token (+ judge calls).

| | Estimate | Actual (from the comparison page "Total spend") |
| --- | --- | --- |
| Pilot | Not recorded | Not recorded |
| Main run | Not recorded | $0.6125 |
| Total | Not recorded | $0.6125 |

All the spend is on B: A runs on a local model priced at 0, and 14 trials × about $0.0438 matches the total. No estimate
was written down before the run.

## Trajectories

Chosen by rule, not by hand. The rule: the lowest trial index where A failed and B passed, on each task, plus the one
failure that is not a wrong answer.

1. **B working:** `csv-aggregate`, trial index 0, B passed (cost $0.056). Trial link: `/trials/ff3d9ffd-bf7c-47f1-88e6-6ff1e05ecc2f`
2. **Same task, A:** `csv-aggregate`, trial index 0, A failed with `wrong_answer`. Trial link: `/trials/b752fd76-e6a1-4725-97d7-cae897c7bdcc`
3. **A surprise:** `config-migrate`, trial index 0, A failed with `gave_up_early`, the only failure of that kind. Trial link:
   `/trials/54bd3278-a420-43da-84ba-752a1842a46d`. The matching B trial passed: `/trials/1a71d813-307e-46ef-9d21-3d88f26f357b`

I have not opened these traces. Read them before drawing conclusions about why A fails.

## Conclusion

The hypothesis held: Claude Code with Haiku passed 14 of 14 trials against 7 of 14 for the baseline harness with local
Qwen2.5 7B, a difference of 50 points (95% CI 14 to 86, bootstrap p = 0.0076). The gap comes mostly from `csv-aggregate`
(2 of 7 against 7 of 7, p = 0.021); on `config-migrate` the 5 of 7 against 7 of 7 difference is within noise. B was also
faster (median 7.8 s against 45.1 s), but it cost about $0.044 per trial while A cost nothing. The main caveat is that
harness and model both differ between A and B, so the result cannot say how much comes from the model and how much from
Claude Code. Other limits: only 2 tasks, neither tests memory, and the token counts (985 against
42,064) may not be comparable, because the two harnesses probably measure usage differently (not checked).
