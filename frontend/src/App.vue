<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">数据安全计算与隐私保护平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向数据脱敏、差分隐私、安全聚合与访问审计的数据安全计算与隐私保护平台。</span>
        <span class="head-user">当前值班：数据工程组</span>
      </header>
      <RouterView v-slot="{ Component, route: currentRoute }">
        <!-- 不同模块路径强制重挂载，避免共享 WorkbenchView 复用导致 moduleKey 不刷新。 -->
        <component :is="Component" :key="currentRoute.path" />
      </RouterView>
    </main>
  </div>
</template>

<script setup lang="ts">
const navItems = [{ label: "运营概览", path: "/" }, { label: "脱敏规则", path: "/mask_rule" }, { label: "隐私预算", path: "/privacy_budget" }, { label: "噪声引擎", path: "/noise_engine" }, { label: "安全聚合", path: "/secure_agg" }, { label: "访问审计", path: "/access_audit" }, { label: "授权审批", path: "/grant_approval" }, { label: "分级分类", path: "/classify_tag" }, { label: "联邦训练", path: "/federated_train" }, { label: "梯度加密", path: "/gradient_encrypt" }, { label: "假名化", path: "/pseudonym" }, { label: "K匿名检查", path: "/k_anonymity" }, { label: "差分查询", path: "/differential_sql" }, { label: "密文索引", path: "/encrypt_index" }, { label: "数据水印", path: "/watermark" }, { label: "同意登记", path: "/consent_registry" }, { label: "风险扫描", path: "/risk_scan" }, { label: "策略下发", path: "/deploy_policy" }, { label: "异常检测", path: "/anomaly_detect" }, { label: "告警核查", path: "/alert_check" }]
</script>
