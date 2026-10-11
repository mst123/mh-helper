<template>
  <main class="page">
    <header class="heading">
      <h1>进度监控</h1>
      <p>每张卡片对应一路 Windows 客户端。开始后会按窗口截图。启动器会点击「开始游戏」。登录页会按配置的账号点「进入游戏」，区服和角色保持默认后再点「登录游戏」。进入主界面后先点右上角头像，记下角色名字、ID 和门派。再打开活动列表看「师门任务」右侧：是「完成」就记到本地、今天不再做；是「参加」才点，然后点「去完成」或「继续任务」。重新上号也会再看一次。师门进行中每 15 秒看一次画面中心，连续两次几乎不变才关弹窗。出现「师门任务完成」后才按 Esc 回到主界面。接着做宝图：活动列表里点「宝图任务」右侧的「参加」或「继续任务」，对话出现后点「听听无妨」。战斗中不按 Esc。</p>
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
          <p class="meta">编号：{{ slot.id }}</p>
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
          </div>
        </el-card>
      </el-col>
    </el-row>
  </main>
</template>

<script setup lang="ts">
import { onMounted } from "vue";

import { useBatchStore } from "../stores/batch";

const store = useBatchStore();

function tagType(status: string) {
  if (status === "执行中") return "success";
  if (status === "暂停") return "warning";
  if (status === "排队" || status === "已停止") return "info";
  return "danger";
}

onMounted(async () => {
  try {
    await store.fetchSlots();
    store.error = "";
  } catch {
    store.error = "连不上执行器。先在 apps/runner 里启动它。";
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

.actions {
  display: flex;
  gap: 8px;
}
</style>
