<template>
  <div class="shell">
    <nav class="nav">
      <router-link to="/">进度</router-link>
      <router-link to="/inspect">识别调试</router-link>
    </nav>
    <router-view />
  </div>
</template>

<style>
body {
  margin: 0;
}

.nav {
  display: flex;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px 24px 0;
}

.nav a {
  color: #606266;
  text-decoration: none;
}

.nav a.router-link-active {
  color: #409eff;
  font-weight: 600;
}
</style>
