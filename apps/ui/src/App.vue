<template>
  <nav>
    <strong>Agent Evals</strong>
    <RouterLink to="/">Home</RouterLink>
    <RouterLink to="/experiments">Experiments</RouterLink>
    <RouterLink to="/experiments/new">New experiment</RouterLink>
    <RouterLink to="/configs">Configs</RouterLink>
  </nav>
  <main><RouterView /></main>
</template>
