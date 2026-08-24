import { createRouter, createWebHistory } from 'vue-router'
import DashboardApp from './App.vue'
import { authState, bootstrapAuth, can } from './auth'
import AdminSystem from './views/AdminSystem.vue'
import AdminUsers from './views/AdminUsers.vue'
import ChangePassword from './views/ChangePassword.vue'
import LoginView from './views/LoginView.vue'
import PublicReports from './views/PublicReports.vue'
import RegisterView from './views/RegisterView.vue'
import AccountSettings from './views/AccountSettings.vue'
import NotificationsView from './views/NotificationsView.vue'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/register', name: 'register', component: RegisterView, meta: { public: true } },
  { path: '/change-password', name: 'change-password', component: ChangePassword },
  { path: '/account', name: 'account', component: AccountSettings },
  { path: '/overview', name: 'overview', component: DashboardApp, meta: { permission: 'overview:read' } },
  { path: '/ai', name: 'ai', component: DashboardApp, meta: { anyPermission: ['ai:basic', 'ai:advanced'] } },
  { path: '/cost-prediction', name: 'cost-prediction', component: DashboardApp, meta: { permission: 'cost_prediction:use' } },
  { path: '/data', name: 'data', component: DashboardApp, meta: { permission: 'data_asset:read' } },
  { path: '/patients', name: 'patients', component: DashboardApp, meta: { permission: 'patient_profile:read' } },
  { path: '/reports', name: 'reports', component: DashboardApp, meta: { permission: 'report:generate' } },
  { path: '/public-reports', name: 'public-reports', component: PublicReports, meta: { permission: 'report:public:read' } },
  { path: '/notifications', name: 'notifications', component: NotificationsView },
  { path: '/admin/users', name: 'admin-users', component: AdminUsers, meta: { permission: 'user:manage' } },
  { path: '/admin/system', name: 'admin-system', component: AdminSystem, meta: { permission: 'system:manage' } },
  { path: '/', redirect: '/overview' },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  if (!authState.ready) await bootstrapAuth()
  if (to.meta.public) return authState.user ? '/overview' : true
  if (!authState.user) return { path: '/login', query: { redirect: to.fullPath } }
  if (authState.user.must_change_password && to.name !== 'change-password') return '/change-password'
  if (to.name === 'change-password') return true
  const allowed = (!to.meta.permission || can(to.meta.permission))
    && (!to.meta.anyPermission || to.meta.anyPermission.some(can))
  return allowed ? true : '/overview'
})

export default router
