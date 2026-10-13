import { createRouter, createWebHistory } from "vue-router";

import InspectView from "../views/Inspect.vue";
import ProgressView from "../views/Progress.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "progress", component: ProgressView },
    { path: "/inspect", name: "inspect", component: InspectView },
  ],
});
