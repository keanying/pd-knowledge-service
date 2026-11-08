<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  IconBookStroked, IconFile, IconCheckList, IconAlertTriangle, IconComment, IconPlus, IconBell, IconChevronRight,
} from '@kousum/semi-icons-vue'
import { api, VERSION_STATUS } from '@/api'
import { useSession } from '@/stores/session'
import KnowledgeArt from '@/components/KnowledgeArt.vue'
import TrendChart from '@/components/TrendChart.vue'
import { formatRelative } from '@/lib/utils'
import { initials, todayText, weekday } from '@/lib/people'

const session = useSession()
const router = useRouter()
const o = ref<Record<string, any> | null>(null)
onMounted(async () => { o.value = await api.overview() })

const stats = computed(() => [
  { label: '知识库', value: o.value?.kb_count, icon: IconBookStroked, color: 'bg-primary', to: '/kbs', perm: 'pdk:kb:view' },
  { label: '文档', value: o.value?.doc_count, icon: IconFile, color: 'bg-cyan', to: '/kbs', perm: 'pdk:kb:view' },
  { label: '待审核', value: o.value?.pending_review, icon: IconCheckList, color: 'bg-pink', to: '/reviews', perm: 'pdk:doc:review' },
  { label: '失败任务', value: o.value?.failed_tasks, icon: IconAlertTriangle, color: 'bg-blue', to: '/tasks', perm: 'pdk:task:manage' },
  { label: '待处理工单', value: o.value?.open_tickets, icon: IconComment, color: 'bg-orange', to: '/tickets', perm: 'pdk:update:review' },
])
const go = (s: { to: string; perm: string }) => session.has(s.perm) && router.push(s.to)

// 发布率：已发布文档 / 全部文档（横幅右侧圆环）
const publishRate = computed(() => {
  const total = o.value?.doc_count || 0
  return total ? Math.round(((o.value?.doc_by_status?.published || 0) / total) * 100) : 0
})
const ring = computed(() => {
  const r = 34, c = 2 * Math.PI * r
  return { r, c, dash: (publishRate.value / 100) * c }
})

// 本周动态：按天分列，事件按状态着色
const week = computed<any[]>(() => o.value?.week ?? [])
const EVENT_COLOR: Record<string, string> = {
  published: 'bg-primary', superseded: 'bg-primary', pending_review: 'bg-pink', failed: 'bg-[#EF4444]', rejected: 'bg-[#EF4444]',
}
const events = computed(() => (o.value?.events ?? []).map((e: any) => {
  const day = e.created_at.slice(0, 10)
  return { ...e, col: Math.max(0, week.value.findIndex((d) => d.date === day)), color: EVENT_COLOR[e.status] || 'bg-cyan' }
}).slice(0, 8))
const today = new Date().toISOString().slice(0, 10)

const trend = computed(() => week.value.map((d) => ({ label: weekday(d.date), value: d.chunks })))
// 头像外圈装饰点
const DOTS = [20, 70, 150, 200, 250, 320].map((a) => [66 + 64 * Math.cos((a * Math.PI) / 180), 66 + 64 * Math.sin((a * Math.PI) / 180)])
const DOC_ICON = ['bg-primary', 'bg-cyan', 'bg-pink', 'bg-blue', 'bg-orange']
</script>

<template>
  <div class="grid grid-cols-[minmax(0,1fr)_340px] gap-6">
    <!-- 左：主内容 -->
    <div class="flex min-w-0 flex-col gap-6">
      <div class="flex items-end justify-between">
        <div>
          <div class="text-[26px] font-bold text-ink">工作台</div>
          <div class="mt-1 text-[13px] text-muted">{{ todayText() }}</div>
        </div>
        <div class="flex items-center gap-4">
          <a v-if="session.has('pdk:task:manage', 'pdk:doc:upload')" class="text-[13px] text-ink" @click="router.push('/tasks')">任务中心 ›</a>
          <button v-if="session.has('pdk:kb:create')" class="pds-btn dark sm" @click="router.push('/kbs?create=1')"><IconPlus />新建知识库</button>
        </div>
      </div>

      <!-- 欢迎横幅 -->
      <div class="relative mt-6 flex h-[150px] items-center rounded-[28px] bg-primary pl-[230px] pr-10 text-white">
        <KnowledgeArt class="absolute -top-9 left-8 h-[180px] w-[200px]" />
        <div class="flex-1">
          <div class="text-[26px]">欢迎回来，<b>{{ session.me?.user.name }}</b></div>
          <div class="mt-2 text-[14px] text-white/80">今天也顺顺利利 · 可访问 {{ session.me?.scenic_scope.length || 0 }} 个景区的知识</div>
        </div>
        <div class="relative flex size-[92px] items-center justify-center">
          <svg viewBox="0 0 92 92" class="absolute inset-0 -rotate-90">
            <circle cx="46" cy="46" :r="ring.r" stroke="rgba(255,255,255,.25)" stroke-width="10" fill="none" />
            <circle cx="46" cy="46" :r="ring.r" stroke="#fff" stroke-width="10" fill="none" stroke-linecap="round"
                    :stroke-dasharray="`${ring.dash} ${ring.c}`" />
          </svg>
          <div class="text-center leading-tight"><div class="text-[18px] font-bold">{{ publishRate }}%</div><div class="text-[11px] text-white/80">已发布</div></div>
        </div>
      </div>

      <!-- 知识概况 -->
      <div>
        <div class="mb-4 flex items-center justify-between">
          <div class="text-[18px] font-bold text-ink">知识概况</div>
          <span class="text-[12px] text-muted">本人可见范围</span>
        </div>
        <div class="grid grid-cols-6 gap-4">
          <button v-for="s in stats" :key="s.label" class="flex cursor-pointer flex-col items-center gap-1 rounded-[22px] border-0 bg-white py-5 transition-shadow hover:shadow-[0_8px_24px_rgba(30,34,53,.08)]" @click="go(s)">
            <span class="flex size-11 items-center justify-center rounded-xl text-white" :class="s.color"><component :is="s.icon" /></span>
            <span class="mt-2 text-[12px] text-muted">{{ s.label }}</span>
            <span class="text-[24px] font-bold text-ink">{{ s.value ?? '—' }}</span>
          </button>
          <button v-if="session.has('pdk:kb:create')" class="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[22px] border-2 border-dashed border-[#B9BBD0] bg-transparent text-[13px] text-muted hover:border-primary hover:text-primary" @click="router.push('/kbs?create=1')">
            <IconPlus size="large" />新建知识库
          </button>
        </div>
      </div>

      <!-- 本周动态 -->
      <div class="rounded-[24px] bg-white px-6 pb-5 pt-5">
        <div class="mb-3 text-center text-[15px] font-semibold text-ink">本周知识动态</div>
        <div class="relative grid grid-cols-7 border-t border-line">
          <div v-for="d in week" :key="d.date" class="relative border-r border-line pb-2 pt-3 text-center last:border-r-0" :class="{ 'is-today': d.date === today }">
            <div class="text-[12px] text-muted">{{ weekday(d.date) }}</div>
            <div class="text-[14px] font-semibold" :class="d.date === today ? 'text-primary' : 'text-ink'">{{ Number(d.date.slice(8)) }}</div>
          </div>
        </div>
        <div class="relative mt-2 grid min-h-[96px] grid-cols-7 gap-y-2">
          <button v-for="(e, i) in events" :key="i" class="flex cursor-pointer flex-col items-start overflow-hidden rounded-xl border-0 px-3 py-2 text-left text-white"
                  :class="e.color" :style="{ gridColumn: `${Math.min(e.col + 1, 6)} / span 2` }" @click="router.push(`/kbs/${e.kb_id}`)">
            <span class="w-full truncate text-[12px] font-medium">{{ e.title }} · v{{ e.version_no }}</span>
            <span class="w-full truncate text-[11px] text-white/80">{{ e.kb_name }} · {{ VERSION_STATUS[e.status]?.[0] || e.status }}</span>
          </button>
          <div v-if="!events.length" class="col-span-7 flex items-center justify-center text-[13px] text-muted">本周还没有文档上传或发布</div>
        </div>
      </div>
    </div>

    <!-- 右：个人栏 -->
    <aside class="flex flex-col rounded-[28px] bg-white px-6 pb-6 pt-6">
      <div class="flex items-center justify-between">
        <span class="text-[16px] font-bold text-ink">我的资料</span>
        <IconBell class="text-muted" />
      </div>
      <div class="mt-5 flex flex-col items-center">
        <div class="relative flex size-[132px] items-center justify-center">
          <svg viewBox="0 0 132 132" class="absolute inset-0">
            <circle cx="66" cy="66" r="58" stroke="#1E2235" stroke-width="2" fill="none" stroke-dasharray="300 64" transform="rotate(-30 66 66)" />
            <circle v-for="(p, i) in DOTS" :key="i" :cx="p[0]" :cy="p[1]" r="2.5" fill="#1E2235" />
          </svg>
          <div class="flex size-[100px] items-center justify-center rounded-full bg-primary-soft text-[28px] font-bold text-primary">{{ initials(session.me?.user.name) }}</div>
        </div>
        <div class="mt-3 text-[16px] font-bold text-ink">{{ session.me?.user.name }}</div>
        <div class="mt-1 text-[12px] text-muted">{{ session.me?.user.emp_no ? `工号 ${session.me.user.emp_no}` : '' }}</div>
      </div>

      <div class="mt-7 flex items-center justify-between">
        <span class="text-[14px] font-semibold text-ink">我最近上传</span>
        <a v-if="session.has('pdk:kb:view')" class="text-[12px] text-muted" @click="router.push('/kbs')">查看全部 <IconChevronRight size="small" /></a>
      </div>
      <div class="mt-3 flex flex-col gap-3">
        <button v-for="(d, i) in o?.my_recent ?? []" :key="d.id" class="flex cursor-pointer items-center gap-3 rounded-2xl border-0 bg-transparent p-1 text-left hover:bg-row" @click="router.push(`/kbs/${d.kb_id}`)">
          <span class="flex size-10 shrink-0 items-center justify-center rounded-xl text-white" :class="DOC_ICON[Number(i) % 5]"><IconFile /></span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-[14px] font-medium text-ink">{{ d.title }}</span>
            <span class="block text-[12px] text-muted">{{ formatRelative(d.updated_at) }}</span>
          </span>
        </button>
        <div v-if="!(o?.my_recent ?? []).length" class="py-4 text-center text-[12px] text-muted">还没有上传过文档</div>
      </div>

      <div class="mt-auto pt-6">
        <TrendChart title="近 7 日新增切片" unit="个" :points="trend" />
      </div>
    </aside>
  </div>
</template>
