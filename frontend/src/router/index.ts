import { createRouter, createWebHistory } from 'vue-router'

import AlertCheckView from '@/views/AlertCheckView.vue'
import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 告警核查页（异常检测工作台的预算告警核查入口），静态路由必须排在 /:moduleKey 之前。
    { path: '/alert_check', name: 'alert-check', component: AlertCheckView },
    { path: '/alert-check', name: 'alert-check-hyphen', component: AlertCheckView },
    { path: '/alert_verification', name: 'alert-verification', component: AlertCheckView },
    { path: '/budget_check', name: 'budget-check', component: AlertCheckView },
    { path: '/verification', name: 'verification', component: AlertCheckView },
    { path: '/anomaly_detect/check', name: 'anomaly-alert-check', component: AlertCheckView },
    { path: '/anomaly_detect/alert_check', name: 'anomaly-alert-check-2', component: AlertCheckView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
