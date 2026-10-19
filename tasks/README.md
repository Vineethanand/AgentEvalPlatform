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

Two kinds of task, reported separately:

- **Reply-only** (most tasks): the result goes in the final reply (a JSON object, a list, a code block) and the grader
  reads `final_answer`. This works the same in every harness, so it measures the model's reasoning, not how a harness
  handles files. Fixtures are still copied into the workspace for the agent to read.
- **File-edit** (tagged `file-edit`: `py-fix-bug`, `config-migrate`, `fs-rename-batch`, `invoice-house-format`): the
  edit is the point, so the agent must change or create files in its workspace and the grader inspects the final
  workspace. The trial's folder (which holds the workspace) is the only thing the sandbox mounts, and the grader reads it after the run.

On the comparison page, use **Show** to see `file-edit tasks only` or `reply-only tasks`
(API: `?tag=file-edit` and `?excludeTag=memory,file-edit`; both parameters accept comma-separated lists).

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
| fs-rename-batch | files | state_check | control; file-edit |
| py-fix-bug | coding | unit_test (hidden tests) | control; file-edit |
| config-migrate | files | state_check | control; file-edit |
| unanswerable-from-docs | reasoning | exact_match ("cannot determine") | hallucination |
| invoice-house-format | skill | state_check | skill: the format exists only in the `invoice-format` skill; file-edit |
| m1-teach-units → m1-use-units | memory chain | state_check | memory: a stated preference (km, one decimal) |
| m2-teach-checks → m2-use-checks | memory chain | state_check + trace_check | memory: a check command only documented in the teach task |
| postmortem-from-logs | writing | llm_judge (rubric) | open-ended output |
| tile-defect | data | state_check | control: find the one wrong pixel in a repeating tile |
| job-schedule | data | state_check | control: order jobs across time zones, peak concurrency |
| dedupe-emails | data | exact_match | control: normalise then count |
| json-diff | data | state_check | control: nested comparison |
| meeting-slots | reasoning | state_check | control: intervals across three calendars |
| test-count-run | tool use | state_check + trace_check | control: the agent must actually run the tests |
| missing-column | reasoning | exact_match ("cannot determine") | hallucination |
| py-add-feature | coding | unit_test (hidden tests) | control; file-edit |
| env-file-update | files | state_check | control; file-edit |
| changelog-house-format | skill | state_check | skill: the format exists only in the `changelog-format` skill |
| m3-teach-ids → m3-use-ids | memory chain | state_check | memory: a ticket id format (TKT- and five digits) |

Teach tasks are unscored. In a memory chain, the use task's workspace lacks the information, so it can
only pass if the agent carried it over in memory.
