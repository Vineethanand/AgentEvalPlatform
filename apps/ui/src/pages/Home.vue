<script setup lang="ts">
const tabs = [
  { to: '/experiments', name: 'Experiments', text: 'Every experiment you have run or queued. Open one to see the verdict (is B better than A?), the pass-rate difference with its confidence interval, cost, failure categories and a dot for every trial.' },
  { to: '/experiments/new', name: 'New experiment', text: 'Start a comparison: pick two or more config versions, choose the tasks, set how many times to repeat each trial, and write your hypothesis before the run.' },
  { to: '/configs', name: 'Configs', text: 'The agent setups you can compare: harness, model and settings such as memory and skills. See the existing configs and their versions, or add a new config; editing one saves a new version, so old results stay valid.' },
];
</script>

<template>
  <h1>Agent Evals Platform</h1>
  <p>
    Compare agent setups fairly. Pick any agent <strong>harness</strong> (baseline, Hermes, Claude Code) and any
    <strong>model</strong>, run each task many times in its own sandbox, grade every run automatically, and get an
    honest answer to: <em>is config B better than config A, by how much, and at what cost?</em>
  </p>

  <div class="panel">
    <h3>How it works</h3>
    <ol>
      <li>Create the configs to compare (<RouterLink to="/configs">Configs</RouterLink>).</li>
      <li>Start an experiment: tasks × configs × repeats (<RouterLink to="/experiments/new">New experiment</RouterLink>).</li>
      <li>Each trial runs in a fresh container and is graded by its task's grader (exact match, unit test, state check, trace check or LLM judge).</li>
      <li>Read the result on the experiment's comparison page, and open any trial to see its full trace.</li>
    </ol>
  </div>

  <div class="panel" v-for="t in tabs" :key="t.to">
    <h3><RouterLink :to="t.to">{{ t.name }}</RouterLink></h3>
    <p class="muted">{{ t.text }}</p>
  </div>

  <div class="panel">
    <h3>Trial dot colours</h3>
    <p class="muted">On an experiment's comparison page every trial is one dot. Click a dot to open that trial.</p>
    <p>
      <span class="dot" style="background: var(--good)"></span> pass ·
      <span class="dot" style="background: var(--bad)"></span> fail ·
      <span class="dot" style="background: var(--harness)"></span> harness error ·
      <span class="dot" style="background: var(--infra)"></span> infrastructure error ·
      <span class="dot" style="background: var(--warn)"></span> running ·
      <span class="dot" style="background: var(--line)"></span> queued
    </p>
  </div>
</template>
