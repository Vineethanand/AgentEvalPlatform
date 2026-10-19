<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { api, usd } from '../api';

const props = defineProps<{ id: string }>();
const data = ref<any>(null);
const pair = ref<any[]>([]);
const open = ref<Record<number, boolean>>({});

async function load() {
  [data.value, pair.value] = await Promise.all([api(`/trials/${props.id}`), api(`/trials/${props.id}/pair`)]);
  open.value = {};
}
watch(() => props.id, load);

// A trial that hasn't finished has no verdict yet: show it as in progress, not as a failure.
const pending = computed(() => ['queued', 'running'].includes(data.value?.trial.status));
const verdict = (t: any) => (['queued', 'running'].includes(t.status) ? 'pending' : t.passed ? 'good' : 'bad');
let timer: number | undefined;
onMounted(() => {
  load();
  timer = window.setInterval(async () => {
    if (!pending.value) return;
    const open0 = open.value;
    await load();
    open.value = open0;
  }, 3000);
});
onUnmounted(() => clearInterval(timer));

const summary = (e: any) => {
  const p = e.payload ?? {};
  switch (e.type) {
    case 'llm_call': return `model call #${p.step ?? ''} · ${p.input_tokens ?? '?'} in / ${p.output_tokens ?? '?'} out tokens`;
    case 'tool_call': return `${p.tool}(${String(p.arguments ?? '').slice(0, 140)})`;
    case 'tool_result': return `${p.tool} → ${p.error ? 'ERROR ' : ''}${String(p.output ?? '').slice(0, 140)}`;
    case 'agent_message': return String(p.content ?? '').slice(0, 200);
    case 'memory_read': return `read memory (${p.store})`;
    case 'memory_write': return `wrote memory (${p.store})`;
    case 'skill_invoked': return `used skill ${p.skill ?? p.tool}`;
    default: return JSON.stringify(p).slice(0, 200);
  }
};
</script>

<template>
  <div v-if="data">
    <h1>{{ data.trial.taskId }} · trial {{ data.trial.trialIndex }}</h1>
    <p>
      <RouterLink :to="`/experiments/${data.trial.experimentId}`">← back to experiment</RouterLink>
      <span v-for="p in pair" :key="p.id"> · <RouterLink :to="`/trials/${p.id}`">same task & trial index, other config ({{ ['queued', 'running'].includes(p.status) ? p.status : p.passed ? 'pass' : 'fail' }})</RouterLink></span>
    </p>

    <div class="panel">
      <table>
        <tr><th>Trial ID</th><td><code style="user-select: all">{{ data.trial.id }}</code>
          <span class="muted"> · as in the worker's Docker logs (attempt {{ data.trial.attempt ?? 1 }})</span></td></tr>
        <tr><th>Config</th><td>{{ data.configVersion.harness }} · {{ data.configVersion.modelAlias }} · memory {{ data.configVersion.settings.memory?.mode }} (v{{ data.configVersion.version }})</td></tr>
        <tr><th>Result</th>
          <td v-if="pending" class="running">{{ data.trial.status }} · in progress
            <span class="muted"> · no result yet</span></td>
          <td v-else :class="data.trial.passed ? 'good' : 'bad'">{{ data.trial.status }} · {{ data.trial.passed ? 'PASS' : 'FAIL' }} · stop: {{ data.trial.stopReason }}
            <span v-if="data.trial.failureCategory"> · failure: {{ data.trial.failureCategory }}</span></td></tr>
        <tr><th>Cost</th><td>{{ usd(data.trial.costUsd) }} · {{ data.trial.tokensIn }} in / {{ data.trial.tokensOut }} out tokens · {{ data.trial.steps }} steps · {{ (data.trial.latencyMs / 1000).toFixed(1) }} s</td></tr>
        <tr><th>Seed / attempt</th><td>{{ data.trial.seed }} / {{ data.trial.attempt }}</td></tr>
        <tr v-if="data.trial.error"><th>Error</th><td><pre>{{ data.trial.error }}</pre></td></tr>
        <tr><th>Final answer</th><td :class="{ muted: pending }"><pre>{{ data.trial.finalAnswer ?? (pending ? 'not available yet' : '') }}</pre></td></tr>
      </table>
    </div>

    <div class="panel">
      <h3>Grades</h3>
      <p v-if="pending && !data.grades.length" class="muted">Not graded yet: grading starts when the trial finishes.</p>
      <div v-for="g in data.grades" :key="g.id" style="margin-bottom: 10px">
        <strong>{{ g.grader }}{{ g.primary ? ' (primary)' : '' }}</strong>:
        <span :class="g.passed ? 'good' : 'bad'">{{ g.passed ? 'pass' : 'fail' }}</span> · score {{ g.score.toFixed(2) }}
        <p v-if="g.raw.ungraded" class="bad">⚠ Not graded: the judge could not be run, so this fail is not a verdict on the answer.
          <span class="muted">{{ g.reasoning }}</span></p>
        <p v-else-if="g.raw.grader_error" class="bad">⚠ Grader error: <span class="muted">{{ g.reasoning }}</span></p>
        <ul><li v-for="c in g.raw.checks ?? []" :key="c.name" :class="c.passed ? 'good' : 'bad'">
          {{ c.passed ? '✓' : '✗' }} {{ c.name }} <span class="muted">{{ c.detail }}</span></li></ul>
      </div>
    </div>

    <div class="panel">
      <h3>Task prompt</h3>
      <pre>{{ data.taskVersion.spec.prompt }}</pre>
    </div>

    <div class="panel">
      <h3>Timeline ({{ data.events.length }} events)</h3>
      <div v-for="e in data.events" :key="e.seq" class="event" :class="e.type" :style="{ marginLeft: e.parentSeq ? '24px' : '0' }">
        <a href="#" @click.prevent="open[e.seq] = !open[e.seq]"><strong>{{ e.type }}</strong></a>
        <span class="muted"> #{{ e.seq }}</span> — {{ summary(e) }}
        <pre v-if="open[e.seq]">{{ JSON.stringify(e.payload, null, 2) }}</pre>
      </div>
    </div>
  </div>
  <p v-else>Loading…</p>
</template>
