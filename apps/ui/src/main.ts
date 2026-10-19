import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';
import App from './App.vue';
import Home from './pages/Home.vue';
import Configs from './pages/Configs.vue';
import Experiments from './pages/Experiments.vue';
import NewExperiment from './pages/NewExperiment.vue';
import Comparison from './pages/Comparison.vue';
import TrialView from './pages/TrialView.vue';
import './style.css';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/configs', component: Configs },
    { path: '/experiments', component: Experiments },
    { path: '/experiments/new', component: NewExperiment },
    { path: '/experiments/:id', component: Comparison, props: true },
    { path: '/trials/:id', component: TrialView, props: true },
  ],
});

createApp(App).use(router).mount('#app');
