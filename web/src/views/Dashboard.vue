<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api'
import { useSession } from '@/stores/session'

const session = useSession()
const router = useRouter()
const o = ref<Record<string, any> | null>(null)
onMounted(async () => { o.value = await api.overview() })

const cards = [
  { key: 'kb_count', label: '知识库', to: '/kbs' },
  { key: 'doc_count', label: '文档', to: '/kbs' },
  { key: 'pending_review', label: '待审核', to: '/reviews' },
  { key: 'failed_tasks', label: '失败任务', to: '/tasks' },
  { key: 'open_tickets', label: '待处理工单', to: '/tickets' },
]
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="pds-card flex items-center justify-between bg-ink! text-white">
      <div>
        <div class="text-[22px] font-semibold">你好，{{ session.me?.user.name }}</div>
        <div class="mt-1 text-[13px] text-[#C9CCCB]">可访问景区：{{ session.me?.scenic_scope.join('、') || '—' }}</div>
      </div>
      <button v-if="session.has('pdk:kb:view')" class="pds-btn accent" @click="router.push('/kbs')">进入知识库</button>
    </div>
    <div class="grid grid-cols-5 gap-5">
      <button v-for="c in cards" :key="c.key" class="pds-card cursor-pointer border-0 text-left transition-shadow hover:shadow-md" @click="router.push(c.to)">
        <div class="pds-muted">{{ c.label }}</div>
        <div class="mt-2 text-[30px] font-semibold text-ink">{{ o?.[c.key] ?? '—' }}</div>
      </button>
    </div>
  </div>
</template>
