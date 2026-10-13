<template>
  <main class="page">
    <header class="heading">
      <h1>进度监控</h1>
      <p>每张卡片对应一路 Windows 客户端。请先自己登录，停在主界面。选择一个任务后点开始，默认是师门。这一轮只跑选中的任务，回到主界面后停止。还没有角色记录时会先点头像。执行中和暂停时不能换任务，也不能清除记录。</p>
    </header>
    <el-alert v-if="store.error" :title="store.error" type="error" show-icon :closable="false" />
    <el-empty v-if="store.slots.length === 0" description="还没有接到执行器上的路" />
    <el-row :gutter="16">
      <el-col v-for="slot in store.slots" :key="slot.id" :xs="24" :sm="12" :lg="8">
        <el-card class="card" shadow="never">
          <template #header>
            <div class="card-title">
              <strong>{{ slot.account_id }}</strong>
              <el-tag :type="tagType(slot.status)">{{ slot.status }}</el-tag>
            </div>
          </template>
          <p class="meta">运行方式：{{ slot.run_mode }}</p>
          <p class="meta">角色：{{ characterLine(slot) }}</p>
          <div class="task-row">
            <span>任务</span>
            <el-select
              :model-value="slot.task_id || 'shimen'"
              :disabled="locked(slot.status)"
              @change="(value: string) => store.selectTask(slot.id, value)"
            >
              <el-option v-for="task in store.tasks" :key="task.id" :label="task.name" :value="task.id" />
            </el-select>
          </div>
          <p v-if="slot.detail" class="detail">{{ slot.detail }}</p>
          <div class="shot">
            <img v-if="slot.screenshot_url" :src="slot.screenshot_url" alt="当前客户区截图" />
            <span v-else>还没有截图</span>
          </div>
          <div class="actions">
            <el-button type="primary" :disabled="slot.status === '执行中'" @click="store.command(slot.id, 'start')">
              开始
            </el-button>
            <el-button :disabled="slot.status !== '执行中'" @click="store.command(slot.id, 'pause')">暂停</el-button>
            <el-button :disabled="slot.status === '排队' || slot.status === '已停止'" @click="store.command(slot.id, 'stop')">
              停止
            </el-button>
            <el-button :disabled="locked(slot.status)" @click="store.clearCharacter(slot.id)">清除当前角色</el-button>
            <el-button :disabled="locked(slot.status)" @click="store.clearToday(slot.id)">清除今日完成</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </main>
</template>

<script setup lang="ts">
import { onMounted } from "vue";

import { useBatchStore } from "../stores/batch";
import type { SlotState } from "../types";

const store = useBatchStore();

function locked(status: string) {
  return status === "执行中" || status === "暂停";
}

function characterLine(slot: SlotState) {
  if (!slot.character_id) return "还没有记录";
  const name = slot.character_name || "未读到名字";
  return `${name}（${slot.character_id}）`;
}

function tagType(status: string) {
  if (status === "执行中") return "success";
  if (status === "暂停") return "warning";
  if (status === "排队" || status === "已停止") return "info";
  return "danger";
}

onMounted(async () => {
  try {
    await store.fetchTasks();
    await store.fetchSlots();
    store.error = "";
  } catch {
    store.error = "连不上执行器。先在 mh/runner 里启动它。";
  }
  store.connect();
});
</script>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.heading h1 {
  margin: 0 0 8px;
  font-size: 24px;
}

.heading p {
  margin: 0 0 16px;
  color: #606266;
}

.card {
  margin-bottom: 16px;
}

.card-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.meta,
.detail {
  margin: 0 0 8px;
  color: #606266;
}

.detail {
  color: #303133;
}

.shot {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 180px;
  margin-bottom: 12px;
  background: #f5f7fa;
  color: #909399;
  overflow: hidden;
}

.shot img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.task-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.task-row span {
  color: #606266;
}

.task-row .el-select {
  width: 160px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
