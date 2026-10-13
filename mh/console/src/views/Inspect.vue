<template>
  <main class="page">
    <header class="heading">
      <h1>识别调试</h1>
      <p>截当前窗口，或上传一张本地图。在图上拖方框，也可以填比例再识别。结果是客户区比例，可以复制。这里不点击，也不改配置。</p>
    </header>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <div class="toolbar">
      <span>这一路</span>
      <el-select v-model="slotId" placeholder="选择一路" style="width: 180px">
        <el-option v-for="slot in store.slots" :key="slot.id" :label="slotLabel(slot)" :value="slot.id" />
      </el-select>
      <el-button type="primary" :loading="capturing" :disabled="!slotId || running" @click="capture">截一张</el-button>
      <el-button :loading="uploading" :disabled="!slotId" @click="pickFile">上传图片</el-button>
      <input ref="fileEl" class="file" type="file" accept="image/*" @change="onFile" />
      <span v-if="running" class="hint">任务还在跑，先停止再截图。上传图片不受影响</span>
      <span v-else-if="shot" class="hint">原图 {{ shot.width }} × {{ shot.height }}</span>
    </div>

    <div v-if="shot" class="work">
      <div class="stage">
        <img ref="imageEl" :src="shot.image_url" alt="调试截图" draggable="false" />
        <div
          class="overlay"
          @mousedown.prevent="onDown"
          @mousemove.prevent="onMove"
          @mouseup.prevent="onUp"
          @mouseleave="onUp"
        >
          <div v-if="region" class="rect" :style="rectStyle" />
          <i v-for="(hit, index) in result?.texts || []" :key="index" class="dot" :style="dotStyle(hit)" :title="hit.text" />
        </div>
      </div>

      <section class="result">
        <div class="range-row">
          <el-input
            v-model="rangeText"
            placeholder="[0.722, 0.627, 0.946, 0.679]"
            @keyup.enter="recognizeRange"
          />
          <el-button type="primary" :loading="reading" @click="recognizeRange">识别</el-button>
        </div>
        <p v-if="region" class="meta">
          范围 左{{ region.x0.toFixed(3) }} 上{{ region.y0.toFixed(3) }} 右{{ region.x1.toFixed(3) }} 下{{ region.y1.toFixed(3) }}
          [{{ regionArray(region) }}]
        </p>
        <p v-if="reading" class="meta">正在认这一块…</p>
        <template v-if="result">
          <p class="swatch-row">
            <i class="swatch" :style="{ background: swatch }" />
            <span>平均色 {{ result.color.r }}, {{ result.color.g }}, {{ result.color.b }}</span>
          </p>
          <p class="meta">绿色像素 {{ result.green }} / {{ result.pixels }}　金色像素 {{ result.gold }} / {{ result.pixels }}</p>
          <ul v-if="result.texts.length" class="texts">
            <li v-for="(hit, index) in result.texts" :key="index">
              {{ hit.text }}　{{ hit.score.toFixed(2) }}　中心 {{ hit.x.toFixed(3) }}, {{ hit.y.toFixed(3) }}
            </li>
          </ul>
          <p v-else class="meta">这一块没有认出文字</p>
          <el-input :model-value="copyText" type="textarea" :rows="8" readonly />
          <el-button @click="copy">复制结果</el-button>
        </template>
        <p v-else-if="!reading" class="meta">在图上拖一个方框，或填上面的比例</p>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { useBatchStore } from "../stores/batch";
import type { SlotState } from "../types";

interface Shot {
  width: number;
  height: number;
  image_url: string;
}

interface Hit {
  text: string;
  score: number;
  x: number;
  y: number;
}

interface RegionResult {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  color: { r: number; g: number; b: number };
  green: number;
  gold: number;
  pixels: number;
  texts: Hit[];
}

interface Region {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

const store = useBatchStore();
const slotId = ref("");
const error = ref("");
const capturing = ref(false);
const uploading = ref(false);
const reading = ref(false);
const shot = ref<Shot | null>(null);
const region = ref<Region | null>(null);
const result = ref<RegionResult | null>(null);
const rangeText = ref("");
const imageEl = ref<HTMLImageElement | null>(null);
const fileEl = ref<HTMLInputElement | null>(null);
const dragging = ref(false);
let anchor = { x: 0, y: 0 };

const current = computed(() => store.slots.find((slot) => slot.id === slotId.value));
const running = computed(() => current.value?.status === "执行中" || current.value?.status === "暂停");
const swatch = computed(() => {
  const color = result.value?.color;
  if (!color) return "#fff";
  return `rgb(${color.r}, ${color.g}, ${color.b})`;
});
const rectStyle = computed(() => {
  const box = region.value;
  if (!box) return {};
  return {
    left: `${box.x0 * 100}%`,
    top: `${box.y0 * 100}%`,
    width: `${(box.x1 - box.x0) * 100}%`,
    height: `${(box.y1 - box.y0) * 100}%`,
  };
});
const copyText = computed(() => {
  const box = result.value;
  if (!box) return "";
  const lines = [
    `范围 左${box.x0.toFixed(3)} 上${box.y0.toFixed(3)} 右${box.x1.toFixed(3)} 下${box.y1.toFixed(3)}`,
    `[${regionArray(box)}]`,
    `平均色 ${box.color.r},${box.color.g},${box.color.b}`,
    `绿色像素 ${box.green} / ${box.pixels}`,
    `金色像素 ${box.gold} / ${box.pixels}`,
    "文字",
  ];
  if (!box.texts.length) {
    lines.push("（没有）");
  }
  for (const hit of box.texts) {
    lines.push(`${hit.text} ${hit.score.toFixed(2)} 中心 ${hit.x.toFixed(3)},${hit.y.toFixed(3)}`);
  }
  return lines.join("\n");
});

function regionArray(box: { x0: number; y0: number; x1: number; y1: number }) {
  return [box.x0, box.y0, box.x1, box.y1].map((value) => value.toFixed(3)).join(", ");
}

function slotLabel(slot: SlotState) {
  return `${slot.account_id}（${slot.status}）`;
}

function dotStyle(hit: Hit) {
  return { left: `${hit.x * 100}%`, top: `${hit.y * 100}%` };
}

function ratioAt(event: MouseEvent) {
  const image = imageEl.value;
  if (!image) return { x: 0, y: 0 };
  const bounds = image.getBoundingClientRect();
  const x = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
  const y = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
  return { x, y };
}

function onDown(event: MouseEvent) {
  dragging.value = true;
  result.value = null;
  anchor = ratioAt(event);
  region.value = { x0: anchor.x, y0: anchor.y, x1: anchor.x, y1: anchor.y };
}

function onMove(event: MouseEvent) {
  if (!dragging.value) return;
  const point = ratioAt(event);
  region.value = {
    x0: Math.min(anchor.x, point.x),
    y0: Math.min(anchor.y, point.y),
    x1: Math.max(anchor.x, point.x),
    y1: Math.max(anchor.y, point.y),
  };
}

function onUp() {
  if (!dragging.value) return;
  dragging.value = false;
  const box = region.value;
  if (!box) return;
  if (box.x1 - box.x0 < 0.01 || box.y1 - box.y0 < 0.01) return;
  rangeText.value = `[${regionArray(box)}]`;
  void recognize(box);
}

function parseRange(raw: string): Region | null {
  const parts = raw
    .replace(/[\[\]（）()]/g, " ")
    .split(/[,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (parts.length !== 4) return null;
  const numbers = parts.map(Number);
  if (numbers.some((value) => !Number.isFinite(value) || value < 0 || value > 1)) return null;
  const [left, top, right, bottom] = numbers;
  return {
    x0: Math.min(left, right),
    y0: Math.min(top, bottom),
    x1: Math.max(left, right),
    y1: Math.max(top, bottom),
  };
}

function recognizeRange() {
  const box = parseRange(rangeText.value);
  if (!box) {
    error.value = "比例要写成四个 0 到 1 的数，例如 [0.722, 0.627, 0.946, 0.679]";
    return;
  }
  if (box.x1 - box.x0 < 0.001 || box.y1 - box.y0 < 0.001) {
    error.value = "这个范围太小";
    return;
  }
  error.value = "";
  region.value = box;
  result.value = null;
  void recognize(box);
}

function pickFile() {
  fileEl.value?.click();
}

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !slotId.value) return;
  error.value = "";
  result.value = null;
  region.value = null;
  uploading.value = true;
  try {
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(`/api/slots/${slotId.value}/inspect/upload`, { method: "POST", body });
    const payload = (await response.json().catch(() => null)) as { detail?: string } | Shot | null;
    if (!response.ok) {
      error.value = (payload as { detail?: string } | null)?.detail || "图片没有换上";
      return;
    }
    shot.value = payload as Shot;
  } catch {
    error.value = "连不上执行器";
  } finally {
    uploading.value = false;
  }
}

async function capture() {
  error.value = "";
  result.value = null;
  region.value = null;
  capturing.value = true;
  try {
    const response = await fetch(`/api/slots/${slotId.value}/inspect/capture`, { method: "POST" });
    const payload = (await response.json().catch(() => null)) as { detail?: string } | Shot | null;
    if (!response.ok) {
      error.value = (payload as { detail?: string } | null)?.detail || "截图没有成功";
      return;
    }
    shot.value = payload as Shot;
  } catch {
    error.value = "连不上执行器";
  } finally {
    capturing.value = false;
  }
}

async function recognize(box: Region) {
  reading.value = true;
  error.value = "";
  try {
    const response = await fetch(`/api/slots/${slotId.value}/inspect/read`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(box),
    });
    const payload = (await response.json().catch(() => null)) as { detail?: string } | RegionResult | null;
    if (!response.ok) {
      error.value = (payload as { detail?: string } | null)?.detail || "这块没有认出来";
      return;
    }
    result.value = payload as RegionResult;
  } catch {
    error.value = "连不上执行器";
  } finally {
    reading.value = false;
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(copyText.value);
  } catch {
    error.value = "没有复制成功，请从文本框里手动复制";
  }
}

onMounted(async () => {
  try {
    await store.fetchSlots();
    slotId.value = store.slots[0]?.id || "";
    error.value = "";
  } catch {
    error.value = "连不上执行器。先在 mh/runner 里启动它。";
  }
  store.connect();
});
</script>

<style scoped>
.page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px;
}

.heading h1 {
  margin: 0 0 8px;
  font-size: 24px;
}

.heading p,
.meta,
.hint {
  margin: 0 0 12px;
  color: #606266;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.toolbar span {
  color: #606266;
}

.file {
  display: none;
}

.range-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.work {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stage {
  position: relative;
  width: 1000px;
  max-width: 100%;
}

.stage img {
  width: 1000px;
  max-width: 100%;
  height: auto;
  display: block;
  background: #f5f7fa;
}

.overlay {
  position: absolute;
  inset: 0;
  cursor: crosshair;
}

.rect {
  position: absolute;
  border: 2px solid #f56c6c;
  background: rgba(245, 108, 108, 0.15);
  box-sizing: border-box;
}

.dot {
  position: absolute;
  width: 8px;
  height: 8px;
  margin: -4px 0 0 -4px;
  border-radius: 50%;
  background: #409eff;
  box-shadow: 0 0 0 1px #fff;
}

.swatch-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.swatch {
  width: 28px;
  height: 18px;
  border: 1px solid #dcdfe6;
}

.texts {
  margin: 0 0 12px;
  padding-left: 18px;
}

.result :deep(.el-textarea) {
  margin-bottom: 8px;
}
</style>
