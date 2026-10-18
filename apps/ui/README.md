# UI (Vue 3 + Vite)

```bash
npm install
npm run dev            # http://localhost:5173, talks to VITE_API_URL (default http://localhost:3000)
```

| Screen | Route | Shows |
| --- | --- | --- |
| Experiments | `/experiments` | All experiments with progress (refreshes every 3 s) |
| New experiment | `/experiments/new` | Pick configs, tasks, N; shows trial count and a cost estimate before launch |
| Comparison | `/experiments/:id` | Verdict banner with Δ and 95% CI, quality vs cost, McNemar table, per-task bars, failure categories, a dot per trial |
| Trial | `/trials/:id` | Result, cost, grades with each check, task prompt, full event timeline, link to the paired trial |
| Configs | `/configs` | Create configs and see their versions |

The UI computes nothing itself: every number comes from the API, so screens and exports always agree.
