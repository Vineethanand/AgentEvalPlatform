# Experiment report: Hermes memory on vs off

## Hypothesis (written before the run)

1. On the memory tasks, memory on passes clearly more often.
2. On the other tasks, pass rates stay about the same.
3. Memory on costs roughly 10–25% more tokens.

## Setup

| Item | Value |
| --- | --- |
| Config A | Hermes, memory off — config version id: |
| Config B | Hermes, memory carry — config version id: |
| Same in both | model ___, temperature 0.7, max 25 steps, 600 s timeout, skills [invoice-format], same seeds |
| Tasks | 10 scored (+2 teach) |
| Trials | N = 10; 20 on the memory chains |
| Hermes commit | |
| Experiment id | |

## Results

Paste from the comparison page (`/experiments/<id>`) or `GET /experiments/<id>/comparison?tag=memory` /
`?excludeTag=memory`.

| Metric | A: memory off | B: memory on | B − A | 95% CI | Verdict |
| --- | --- | --- | --- | --- | --- |
| Pass rate, memory tasks | | | | | |
| Pass rate, other tasks | | | | | |
| Pass rate, all tasks | | | | | |
| Cost per trial (USD) | | | | | |
| Tokens per trial | | | | | |

McNemar (all tasks): only A ___, only B ___, p = ___

## Cost

Formula: tasks × trials × configs × average tokens per trial × price per token (+ judge calls).

| | Estimate | Actual (from the comparison page "Total spend") |
| --- | --- | --- |
| Pilot | | |
| Main run | | |
| Total | | |

## Trajectories

Chosen by rule, not by hand:

1. **Memory working** — a memory-on pass on m2-use-checks that reads the saved command. Trial link:
2. **Same task, memory off** — the same trial index with memory off. Trial link:
3. **A surprise** — a memory-on failure, e.g. memory written but never read. Trial link:

## Conclusion

One paragraph: which hypotheses held, the size of the difference and its CI, the cost, and the main caveat
(only two memory chains, one model).
