import { defineStore } from "pinia";
import { ref } from "vue";

import type { SlotState } from "../types";

export const useBatchStore = defineStore("batch", () => {
  const slots = ref<SlotState[]>([]);
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

  return { slots, error, fetchSlots, connect, command };
});
