import { defineStore } from "pinia";
import { ref } from "vue";

import type { SlotState } from "../types";

export const useBatchStore = defineStore("batch", () => {
  const slots = ref<SlotState[]>([]);
  const tasks = ref<{ id: string; name: string }[]>([]);
  const error = ref("");
  let socket: WebSocket | null = null;
  let reconnectTimer = 0;

  function apply(next: SlotState[]) {
    slots.value = next;
  }

  async function fetchSlots() {
    const response = await fetch("/api/slots");
    if (!response.ok) {
      throw new Error("执行器没有返回各路状态");
    }
    apply((await response.json()) as SlotState[]);
  }

  function connect() {
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${location.host}/ws`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { type?: string; slots?: SlotState[] };
      if (payload.type === "slots" && payload.slots) {
        apply(payload.slots);
        error.value = "";
      }
    };
    socket.onclose = () => {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connect, 1000);
    };
  }

  async function fetchTasks() {
    const response = await fetch("/api/tasks");
    if (!response.ok) {
      throw new Error("执行器没有返回任务列表");
    }
    tasks.value = (await response.json()) as { id: string; name: string }[];
  }

  async function postSlot(id: string, path: string, body?: unknown) {
    error.value = "";
    const response = await fetch(`/api/slots/${id}/${path}`, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      error.value = payload?.detail || "操作没有送进执行器";
      await fetchSlots().catch(() => undefined);
      return;
    }
    await fetchSlots();
  }

  function selectTask(id: string, task: string) {
    return postSlot(id, "task", { task });
  }

  function clearCharacter(id: string) {
    return postSlot(id, "clear-character");
  }

  function clearToday(id: string) {
    return postSlot(id, "clear-today");
  }

  async function command(id: string, action: "start" | "pause" | "stop") {
    error.value = "";
    const response = await fetch(`/api/slots/${id}/${action}`, { method: "POST" });
    if (!response.ok) {
      error.value = "操作没有送进执行器";
      return;
    }
    // 开始只是把命令放进队列，接口立刻返回的还是旧状态。稍后拉一次，卡片不用干等推送。
    window.setTimeout(() => {
      void fetchSlots().catch(() => {
        error.value = "执行器没有返回各路状态";
      });
    }, 600);
  }

  return { slots, tasks, error, fetchSlots, fetchTasks, connect, command, selectTask, clearCharacter, clearToday };
});
