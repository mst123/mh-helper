import { createRouter, createWebHistory } from "vue-router";

import ProgressView from "../views/Progress.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: "/", name: "progress", component: ProgressView }],
});
