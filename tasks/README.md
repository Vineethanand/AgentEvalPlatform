# Tasks

One folder per task. Adding a task = adding a folder; `POST /tasks/sync` picks it up and creates a new
task version whenever its content changes.

```
tasks/<id>/
  task.yaml          prompt, tags, timeout, graders (one marked primary)
  fixtures/          copied into the agent's fresh workspace
  grader/            check.py for state_check, tests/ for unit_test (hidden from the agent)
  reference/         a known-good solution: MUST pass the primary grader
  negatives/<name>/  known-bad solutions: MUST fail it
tasks/_skills/<name>/SKILL.md   skill bundles a config can enable
```

A solution folder holds `workspace/` (final files), `answer.txt` (final answer) and/or `events.jsonl` (trace).
Check every grader with:

```bash
python scripts/validate_tasks.py              # all tasks
python scripts/validate_tasks.py --with-judge # also LLM-judged tasks (needs the gateway)
```

## task.yaml

```yaml
id: csv-aggregate               # must match the folder name
title: Revenue per region from a CSV
prompt: |
  ...
tags: [tool-use, data, control] # "memory" and "skill" tags enable the matching failure rules
timeout_s: 300
scored: true                    # false for a memory chain's "teach" task
chain: m1                       # memory chain id (optional)
chain_order: 2                  # position in the chain
graders:
  - type: state_check           # exact_match | unit_test | state_check | trace_check | llm_judge
    primary: true
```

## The sample set

| Task | Kind | Primary grader | Built to show |
| --- | --- | --- | --- |
| csv-aggregate | data | state_check | control |
| log-triage | data | exact_match | control |
| fs-rename-batch | files | state_check | control |
| py-fix-bug | coding | unit_test (hidden tests) | control |
| config-migrate | files | state_check | control |
| unanswerable-from-docs | reasoning | exact_match ("cannot determine") | hallucination |
| invoice-house-format | skill | state_check | skill: the format exists only in the `invoice-format` skill |
| m1-teach-units → m1-use-units | memory chain | state_check | memory: a stated preference (km, one decimal) |
| m2-teach-checks → m2-use-checks | memory chain | state_check + trace_check | memory: a check command only documented in the teach task |
| postmortem-from-logs | writing | llm_judge (rubric) | open-ended output |

Teach tasks are unscored. In a memory chain, the use task's workspace lacks the information, so it can
only pass if the agent carried it over in memory.
