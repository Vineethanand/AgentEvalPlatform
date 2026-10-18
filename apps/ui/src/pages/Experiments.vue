<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { api } from '../api';

const experiments = ref<any[]>([]);
let timer: number | undefined;
const load = async () => { experiments.value = await api('/experiments'); };
onMounted(() => { load(); timer = window.setInterval(load, 3000); });
onUnmounted(() => clearInterval(timer));
const total = (p: Record<string, number>) => Object.values(p).reduce((s, n) => s + n, 0);
</script>

<template>
  <h1>Experiments</h1>
  <div class="panel">
    <table>
      <tr><th>Name</th><th>Status</th><th>Progress</th><th>Trials per task</th><th>Created</th></tr>
      <tr v-for="e in experiments" :key="e.id">
        <td><RouterLink :to="`/experiments/${e.id}`">{{ e.name }}</RouterLink><div class="muted">{{ e.hypothesis }}</div></td>
        <td>{{ e.status }}</td>
        <td>
          {{ (e.progress.done ?? 0) }} / {{ total(e.progress) }} done
          <span class="bad" v-if="e.progress.infra_error || e.progress.harness_error">
            · {{ (e.progress.infra_error ?? 0) + (e.progress.harness_error ?? 0) }} errors
          </span>
        </td>
        <td>{{ e.nTrials }}</td>
        <td class="muted">{{ new Date(e.createdAt).toLocaleString() }}</td>
      </tr>
      <tr v-if="!experiments.length"><td colspan="5" class="muted">No experiments yet. Create configs, then a new experiment.</td></tr>
    </table>
  </div>
</template>
