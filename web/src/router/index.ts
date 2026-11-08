import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useSession } from '@/stores/session'
import AppLayout from '@/layout/AppLayout.vue'
import { menuGroups } from '@/layout/menu'

/** 骨架阶段未实现的菜单统一指向“建设中”页面。 */
const todoRoutes: RouteRecordRaw[] = menuGroups.flatMap((g) => g.children.filter((c) => c.todo)).map((c) => ({
  path: c.path.slice(1), component: () => import('@/views/Todo.vue'), meta: { title: c.title, perms: c.perms },
}))

/** meta.perms：满足其一即可访问（与 PDS 中的 PDK 权限点一致；后端接口同样强制校验） */
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '工作台', perms: ['pdk:console:access'] } },
      { path: 'kbs', name: 'kbs', component: () => import('@/views/KbList.vue'), meta: { title: '知识库', perms: ['pdk:kb:view'] } },
      { path: 'kbs/:id', name: 'kb', component: () => import('@/views/KbDetail.vue'), meta: { title: '知识库详情', perms: ['pdk:kb:view'] } },
      { path: 'reviews', name: 'reviews', component: () => import('@/views/Reviews.vue'), meta: { title: '审核中心', perms: ['pdk:doc:review'] } },
      { path: 'tickets', name: 'tickets', component: () => import('@/views/Tickets.vue'), meta: { title: '纠错工单', perms: ['pdk:update:review', 'pdk:kb:view'] } },
      { path: 'tasks', name: 'tasks', component: () => import('@/views/Tasks.vue'), meta: { title: '任务中心', perms: ['pdk:task:manage', 'pdk:doc:upload'] } },
      { path: 'api-keys', name: 'apiKeys', component: () => import('@/views/ApiKeys.vue'), meta: { title: '接口密钥', perms: ['pdk:apikey:manage'] } },
      ...todoRoutes,
      { path: 'forbidden', name: 'forbidden', component: () => import('@/views/Forbidden.vue'), meta: { title: '无权访问' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })

router.beforeEach(async (to) => {
  const session = useSession()
  if (!session.me) {
    try {
      await session.load() // 未登录时接口返回 401，http 拦截器会跳转统一登录
    } catch {
      return false
    }
  }
  const perms = to.meta.perms as string[] | undefined
  if (perms && !session.has(...perms)) return { name: 'forbidden' }
  return true
})
