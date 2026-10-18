<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { API, api, pct, pts, usd } from '../api';

const props = defineProps<{ id: string }>();
const detail = ref<any>(null);
const cmp = ref<any>(null);
const filter = ref<'all' | 'memory' | 'control'>('all');
let timer: number | undefined;

async function load() {
  const q = filter.value === 'memory' ? '?tag=memory' : filter.value === 'control' ? '?excludeTag=memory' : '';
  [detail.value, cmp.value] = await Promise.all([api(`/experiments/${props.id}`), api(`/experiments/${props.id}/comparison${q}`)]);
  if (['done', 'incomplete', 'cancelled'].includes(detail.value.experiment.status)) clearInterval(timer);
}
watch(filter, load);
onMounted(() => { load(); timer = window.setInterval(load, 3000); });
onUnmounted(() => clearInterval(timer));

const bannerClass = computed(() => {
  const v = cmp.value?.verdict ?? '';
  return v === 'B better' ? 'b' : v === 'A better' ? 'a' : v.startsWith('withheld') ? 'withheld' : 'none';
});
const label = (cv: any) => (cv ? `${cv.harness} · ${cv.modelAlias} · memory ${cv.settings?.memory?.mode ?? 'off'}` : '');
const nameOf = (id: string) => {
  const i = detail.value?.experiment.configVersionIds.indexOf(id);
  return i === 0 ? 'A' : i === 1 ? 'B' : `C${i}`;
};
// Delta bar: centred at 0, from -100 to +100 points.
const barStyle = (d: number) => ({ left: `${50 + Math.min(0, d) * 50}%`, width: `${Math.abs(d) * 50}%`, background: d >= 0 ? 'var(--good)' : 'var(--bad)' });
const dotColor = (t: any) => t.status === 'queued' ? 'var(--line)' : t.status === 'running' ? 'var(--warn)' :
  t.status !== 'done' ? 'var(--bad)' : t.passed ? 'var(--good)' : 'var(--muted)';
const grid = computed(() => {
  const rows: Record<string, Record<string, any[]>> = {};
  for (const t of detail.value?.trials ?? []) {
    rows[t.taskId] ??= {};
    (rows[t.taskId][t.configVersionId] ??= []).push(t);
  }
  return rows;
});
const categories = computed(() => [...new Set([...Object.keys(cmp.value?.failureCategories.a ?? {}), ...Object.keys(cmp.value?.failureCategories.b ?? {})])]);
</script>

<template>
  <div v-if="detail && cmp">
    <h1>{{ detail.experiment.name }}</h1>
    <p class="muted">{{ detail.experiment.hypothesis }} · status: {{ detail.experiment.status }}</p>

    <p>
      Show:
      <select v-model="filter">
        <option value="all">all scored tasks</option>
        <option value="memory">memory tasks only</option>
        <option value="control">all except memory tasks</option>
      </select>
      · <a :href="`${API}/experiments/${id}/export?format=csv`">Export CSV</a>
      · <a :href="`${API}/experiments/${id}/export?format=json`">Export JSON</a>
    </p>

    <div class="banner" :class="bannerClass">
      {{ cmp.verdict }} · Δ = {{ pts(cmp.delta) }}, 95% CI [{{ pts(cmp.ci95[0]) }}, {{ pts(cmp.ci95[1]) }}]
      <div class="muted" style="font-size: 14px; font-weight: 400">
        A = {{ label(cmp.a) }} &nbsp;|&nbsp; B = {{ label(cmp.b) }} · {{ cmp.tasks }} tasks, {{ cmp.pairs }} paired trials
      </div>
    </div>

    <div class="grid2">
      <div class="panel">
        <h3>Quality and cost</h3>
        <table>
          <tr><th></th><th>A</th><th>B</th><th>B − A (95% CI)</th></tr>
          <tr><td>Pass rate</td><td>{{ pct(cmp.passRate.a) }}</td><td>{{ pct(cmp.passRate.b) }}</td>
            <td>{{ pts(cmp.delta) }} [{{ pts(cmp.ci95[0]) }}, {{ pts(cmp.ci95[1]) }}]</td></tr>
          <tr><td>Cost / trial</td><td>{{ usd(cmp.cost.meanA) }}</td><td>{{ usd(cmp.cost.meanB) }}</td>
            <td>{{ usd(cmp.cost.delta) }} [{{ usd(cmp.cost.ci95[0]) }}, {{ usd(cmp.cost.ci95[1]) }}]</td></tr>
          <tr><td>Tokens / trial</td><td>{{ Math.round(cmp.tokens.meanA || 0) }}</td><td>{{ Math.round(cmp.tokens.meanB || 0) }}</td>
            <td>{{ Math.round(cmp.tokens.delta || 0) }}</td></tr>
          <tr><td>Median latency</td><td>{{ (cmp.latencyMs.medianA / 1000).toFixed(1) }} s</td><td>{{ (cmp.latencyMs.medianB / 1000).toFixed(1) }} s</td><td></td></tr>
          <tr><td>Infra failures (excluded)</td><td>{{ cmp.infraFailures.a }}</td><td>{{ cmp.infraFailures.b }}</td><td></td></tr>
          <tr><td>Total spend</td><td colspan="3">{{ usd(cmp.totalSpendUsd) }}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h3>McNemar cross-check (one outcome per task)</h3>
        <table>
          <tr><th></th><th>B passes</th><th>B fails</th></tr>
          <tr><th>A passes</th><td>{{ cmp.mcnemar.bothPass }}</td><td><strong>{{ cmp.mcnemar.onlyA }}</strong></td></tr>
          <tr><th>A fails</th><td><strong>{{ cmp.mcnemar.onlyB }}</strong></td><td>{{ cmp.mcnemar.neither }}</td></tr>
        </table>
        <p>p = {{ cmp.mcnemar.p.toFixed(3) }} <span class="muted">(only the bold disagreement cells matter)</span></p>
      </div>
    </div>

    <div class="panel">
      <h3>Per task</h3>
      <table>
        <tr><th>Task</th><th>A</th><th>B</th><th>Δ</th><th style="width: 30%">−100 … 0 … +100 pts</th><th>p (Fisher)</th></tr>
        <tr v-for="r in cmp.perTask" :key="r.taskId">
          <td>{{ r.taskId }}</td><td>{{ r.passA }}/{{ r.nA }}</td><td>{{ r.passB }}/{{ r.nB }}</td><td>{{ pts(r.delta) }}</td>
          <td><div class="bar"><span :style="barStyle(r.delta)"></span></div></td>
          <td :class="r.label === 'significant' ? 'good' : 'muted'">{{ r.p.toFixed(3) }} {{ r.label }}</td>
        </tr>
      </table>
      <p class="muted">With few trials per task, only large per-task swings can be told apart from noise.</p>
    </div>

    <div class="panel">
      <h3>Why trials failed</h3>
      <table>
        <tr><th>Category</th><th>A</th><th>B</th></tr>
        <tr v-for="c in categories" :key="c"><td>{{ c }}</td><td>{{ cmp.failureCategories.a[c] ?? 0 }}</td><td>{{ cmp.failureCategories.b[c] ?? 0 }}</td></tr>
      </table>
    </div>

    <div class="panel">
      <h3>All trials</h3>
      <p class="muted">green = pass · grey = fail · amber = running · red = error. Click a dot to inspect the trial.</p>
      <table>
        <tr><th>Task</th><th v-for="cv in detail.experiment.configVersionIds" :key="cv">{{ nameOf(cv) }}</th></tr>
        <tr v-for="(byCfg, taskId) in grid" :key="taskId">
          <td>{{ taskId }}</td>
          <td v-for="cv in detail.experiment.configVersionIds" :key="cv">
            <RouterLink v-for="t in byCfg[cv] ?? []" :key="t.id" :to="`/trials/${t.id}`" :title="`trial ${t.trialIndex}: ${t.status}${t.failureCategory ? ' · ' + t.failureCategory : ''}`">
              <span class="dot" :style="{ background: dotColor(t) }"></span>
            </RouterLink>
          </td>
        </tr>
      </table>
    </div>
  </div>
  <p v-else>Loading…</p>
</template>
