<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api, post } from '../api';

const configs = ref<any[]>([]);
const models = ref<any[]>([]);
const harnesses = ref<Record<string, any>>({});
const error = ref('');
const form = ref({
  name: '', description: '', harness: 'baseline', modelAlias: '',
  settings: JSON.stringify({
    temperature: 0.7, max_steps: 25, max_tokens_total: 200000, timeout_s: 600,
    tools: ['bash', 'read_file', 'write_file', 'list_dir'], skills: [], memory: { mode: 'off' },
  }, null, 2),
});

async function load() {
  [configs.value, models.value, harnesses.value] = await Promise.all([api('/configs'), api('/models'), api('/harnesses')]);
  if (!form.value.modelAlias && models.value.length) form.value.modelAlias = models.value[0].alias;
}

async function create() {
  error.value = '';
  try {
    await post('/configs', { ...form.value, settings: JSON.parse(form.value.settings) });
    form.value.name = '';
    await load();
  } catch (e: any) { error.value = e.message; }
}

onMounted(load);
</script>

<template>
  <h1>Configs</h1>
  <p class="muted">A config = harness + model + settings. Versions are immutable: changing a config creates a new version.</p>

  <div class="panel">
    <h3>New config</h3>
    <div class="grid2">
      <div>
        <label>Name</label><input v-model="form.name" placeholder="hermes-sonnet-mem-off" style="width: 100%" />
        <label>Description</label><input v-model="form.description" style="width: 100%" />
        <label>Harness</label>
        <select v-model="form.harness">
          <option v-for="(h, name) in harnesses" :key="name" :value="name">{{ name }} ({{ h.capabilities.join(', ') }})</option>
        </select>
        <label>Model</label>
        <select v-model="form.modelAlias">
          <option v-for="m in models" :key="m.alias" :value="m.alias">
            {{ m.alias }} — {{ m.litellmModel }} (${{ m.priceInputPerMtok }} / ${{ m.priceOutputPerMtok }} per Mtok)
          </option>
        </select>
      </div>
      <div>
        <label>Settings (JSON)</label>
        <textarea v-model="form.settings" rows="12" style="width: 100%; font-family: monospace"></textarea>
        <p class="muted">memory.mode: off | fresh | carry. carry keeps memory across a teach → use chain.</p>
      </div>
    </div>
    <button class="primary" @click="create">Create</button>
    <span class="bad" v-if="error"> {{ error }}</span>
  </div>

  <div class="panel" v-for="c in configs" :key="c.id">
    <h3>{{ c.name }} <span class="muted">{{ c.description }}</span></h3>
    <table>
      <tr><th>Version</th><th>Harness</th><th>Model</th><th>Settings</th><th>Version id</th></tr>
      <tr v-for="v in c.versions" :key="v.id">
        <td>v{{ v.version }}</td><td>{{ v.harness }}</td><td>{{ v.modelAlias }}</td>
        <td><pre>{{ JSON.stringify(v.settings) }}</pre></td><td class="muted">{{ v.id }}</td>
      </tr>
    </table>
  </div>
</template>
