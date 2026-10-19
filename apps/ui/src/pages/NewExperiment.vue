<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { api, post } from '../api';

const router = useRouter();
const tasks = ref<any[]>([]);
const configs = ref<any[]>([]);
const models = ref<any[]>([]);
const error = ref('');
const form = ref({ name: '', hypothesis: '', nTrials: 10, seed: 1234, taskIds: [] as string[], configVersionIds: [] as string[], nOverrides: '{}' });

async function load() {
  await post('/tasks/sync', {});
  [tasks.value, configs.value, models.value] = await Promise.all([api('/tasks'), api('/configs'), api('/models')]);
  form.value.taskIds = tasks.value.map((t) => t.id);
}

const versions = computed(() => configs.value.flatMap((c) => c.versions.map((v: any) => ({ ...v, label: `${c.name} v${v.version}` }))));

// Rough estimate: assumed 40k input + 3k output tokens per trial; the pilot replaces these with measured numbers.
const estimate = computed(() => {
  const perConfig = form.value.taskIds.length * form.value.nTrials;
  return form.value.configVersionIds.reduce((sum, id) => {
    const v = versions.value.find((x) => x.id === id);
    const m = v && models.value.find((x) => x.alias === v.modelAlias);
    if (!m) return sum;
    return sum + perConfig * (40000 * m.priceInputPerMtok + 3000 * m.priceOutputPerMtok) / 1e6;
  }, 0);
});

// Default name = the selected configs in order, e.g. "hermes-sonnet v1 vs hermes-qwen v2".
const defaultName = computed(() => form.value.configVersionIds
  .map((id) => versions.value.find((v) => v.id === id)?.label).filter(Boolean).join(' vs '));

async function launch() {
  error.value = '';
  try {
    const name = form.value.name.trim() || defaultName.value;
    const res = await post('/experiments', { ...form.value, name, nOverrides: JSON.parse(form.value.nOverrides) });
    router.push(`/experiments/${res.experiment.id}`);
  } catch (e: any) { error.value = e.message; }
}

onMounted(load);
</script>

<template>
  <h1>New experiment</h1>
  <div class="panel">
    <label>Name</label><input v-model="form.name" style="width: 100%" :placeholder="defaultName || 'Select configs to get a default name, e.g. A vs B'" />
    <p class="muted" v-if="!form.name.trim() && defaultName">Left blank, the name will be: {{ defaultName }}</p>
    <label>Hypothesis (write it before running)</label>
    <textarea v-model="form.hypothesis" rows="2" style="width: 100%"></textarea>

    <div class="grid2">
      <div>
        <label>Configs to compare (first = A, second = B)</label>
        <div v-for="v in versions" :key="v.id">
          <input type="checkbox" :value="v.id" v-model="form.configVersionIds" /> {{ v.label }}
          <span class="muted">({{ v.harness }}, {{ v.modelAlias }}, memory {{ v.settings.memory?.mode }})</span>
        </div>
        <label>Trials per task (N)</label><input type="number" v-model.number="form.nTrials" min="1" />
        <label>Per-task N overrides (JSON, e.g. {"m1-use-units": 20})</label>
        <input v-model="form.nOverrides" style="width: 100%" />
        <label>Seed</label><input type="number" v-model.number="form.seed" />
      </div>
      <div>
        <label>Tasks</label>
        <div v-for="t in tasks" :key="t.id">
          <input type="checkbox" :value="t.id" v-model="form.taskIds" /> {{ t.id }}
          <span class="muted">{{ t.tags.join(', ') }}</span>
        </div>
      </div>
    </div>
    <p>
      {{ form.taskIds.length }} tasks × {{ form.nTrials }} trials × {{ form.configVersionIds.length }} configs =
      <strong>{{ form.taskIds.length * form.nTrials * form.configVersionIds.length }} trials</strong>,
      estimated cost <strong>${{ estimate.toFixed(2) }}</strong>
      <span class="muted">(assumes 40k in / 3k out tokens per trial)</span>
    </p>
    <button class="primary" @click="launch" :disabled="form.configVersionIds.length < 2">Launch</button>
    <span class="bad" v-if="error"> {{ error }}</span>
  </div>
</template>
