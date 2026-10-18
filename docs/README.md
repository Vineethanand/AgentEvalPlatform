# Docs

- **Design document:** https://claude.ai/code/artifact/cc199579-0aee-49b9-affb-75e3e7eacea1
  (architecture, adapters, data model, isolation, graders, statistics, cost, known limits, experiment plan).
- **Experiment report:** fill in [`experiment-report.md`](experiment-report.md) after the run.

## Judge calibration (do this before trusting LLM-judged tasks)

1. Run a pilot (N=3) on both configs.
2. Export the judged trials (`GET /experiments/:id/export?format=json`) and sample about 60 answers.
3. Grade them yourself with the same rubric, without looking at the config or the judge's verdict.
4. Compare: agreement %, and how often the judge passed something you failed.
5. If agreement is low, tighten the rubric wording and repeat on fresh examples.
   Report judged tasks separately until the judge agrees with you on most examples.
