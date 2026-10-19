<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api, post } from '../api';

const configs = ref<any[]>([]);
const models = ref<any[]>([]);
const harnesses = ref<Record<string, any>>({});
const error = ref('');
const success = ref('');
let successTimer: number | undefined;
const editingId = ref<string | null>(null);
const blankForm = () => ({
  name: '', description: '', harness: 'baseline', modelAlias: '',
  settings: JSON.stringify({
    temperature: 0.7, max_steps: 25, max_tokens_total: 200000, timeout_s: 600,
    tools: ['bash', 'read_file', 'write_file', 'list_dir'], skills: [], memory: { mode: 'off' },
  }, null, 2),
});
const form = ref(blankForm());

/** Load a config's latest version into the form. Saving creates the next version. */
function startEdit(c: any) {
  const v = c.versions[0];
  editingId.value = c.id;
  form.value = { name: c.name, description: c.description, harness: v.harness, modelAlias: v.modelAlias, settings: JSON.stringify(v.settings, null, 2) };
  error.value = ''; success.value = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function cancelEdit() {
  editingId.value = null;
  form.value = { ...blankForm(), modelAlias: models.value[0]?.alias ?? '' };
}

async function load() {
  [configs.value, models.value, harnesses.value] = await Promise.all([api('/configs'), api('/models'), api('/harnesses')]);
  if (!form.value.modelAlias && models.value.length) form.value.modelAlias = models.value[0].alias;
}

async function remove(c: any) {
  if (!window.confirm(`Delete config "${c.name}" and its ${c.versions.length} version(s)?`)) return;
  error.value = '';
  try { await api(`/configs/${c.id}`, { method: 'DELETE' }); await load(); }
  catch (e: any) { error.value = e.message; }
}

async function save() {
  error.value = ''; success.value = '';
  try {
    const name = form.value.name;
    const body = { ...form.value, settings: JSON.parse(form.value.settings) };
    if (editingId.value) {
      const before = configs.value.find((c) => c.id === editingId.value)?.versions.length ?? 0;
      await post(`/configs/${editingId.value}/versions`, body);
      await load();
      const after = configs.value.find((c) => c.id === editingId.value)?.versions.length ?? 0;
      success.value = after > before ? `Config "${name}" was updated: saved as a new version.` : `Config "${name}" is unchanged: no new version was created.`;
      cancelEdit();
    } else {
      await post('/configs', body);
      form.value.name = '';
      await load();
      success.value = `Config "${name}" was added to the existing list of configs.`;
    }
    clearTimeout(successTimer);
    successTimer = window.setTimeout(() => { success.value = ''; }, 8000);
  } catch (e: any) { error.value = e.message; }
}

onMounted(load);
</script>

<template>
  <h1>Configs</h1>
  <p class="bad" v-if="error">{{ error }}</p>
  <p class="muted">A config = harness + model + settings. Versions are immutable: changing a config creates a new version.</p>

  <div class="panel">
    <h3>{{ editingId ? `Edit config: ${form.name}` : 'New config' }}</h3>
    <p class="muted" v-if="editingId">Saving creates a new version. Name and description stay as they are; earlier versions and experiments that used them are untouched.</p>
    <div class="grid2">
      <div>
        <label>Name</label><input v-model="form.name" :disabled="!!editingId" placeholder="hermes-sonnet-mem-off" style="width: 100%" />
        <label>Description</label><input v-model="form.description" :disabled="!!editingId" style="width: 100%" />
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
    <button class="primary" @click="save">{{ editingId ? 'Save as new version' : 'Create' }}</button>
    <button v-if="editingId" @click="cancelEdit">Cancel</button>
    <span class="bad" v-if="error"> {{ error }}</span>
    <span class="good" v-if="success"> ✓ {{ success }}</span>
  </div>

  <div class="panel" v-for="c in configs" :key="c.id">
    <h3>{{ c.name }} <span class="muted">{{ c.description }}</span>
      <span style="float: right"><button @click="startEdit(c)">Edit</button> <button @click="remove(c)">Delete</button></span></h3>
    <table>
      <tr><th>Version</th><th>Harness</th><th>Model</th><th>Settings</th><th>Version id</th></tr>
      <tr v-for="v in c.versions" :key="v.id">
        <td>v{{ v.version }}</td><td>{{ v.harness }}</td><td>{{ v.modelAlias }}</td>
        <td><pre>{{ JSON.stringify(v.settings) }}</pre></td><td class="muted">{{ v.id }}</td>
      </tr>
    </table>
  </div>
</template>
