import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
    },
    {
      path: '/ai',
      name: 'ai-chat',
      component: () => import('../views/AIChatView.vue'),
    },
    {
      path: '/data-quality',
      name: 'data-quality',
      component: () => import('../views/DataQualityView.vue'),
    },
    {
      path: '/cost-prediction',
      name: 'cost-prediction',
      component: () => import('../views/CostPredictionView.vue'),
    },
  ],
})
