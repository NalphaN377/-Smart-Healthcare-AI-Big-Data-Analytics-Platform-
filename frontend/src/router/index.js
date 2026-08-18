import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from '../views/DashboardView.vue'
import AIChatView from '../views/AIChatView.vue'
import DataQualityView from '../views/DataQualityView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView },
    { path: '/ai', name: 'ai-chat', component: AIChatView },
    { path: '/data-quality', name: 'data-quality', component: DataQualityView },
  ],
})
