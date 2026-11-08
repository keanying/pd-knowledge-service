<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '@/api'
import { formatTime } from '@/lib/utils'

const list = ref<any[]>([])
async function load() { list.value = await api.tickets() }
onMounted(load)
const TYPE: Record<string, string> = { correction: '纠错', suggestion: '更新建议', gap: '知识缺口' }
async function close(t: any) { await api.updateTicket(t.id, { status: 'closed' }); await load() }
</script>

<template>
  <div class="pds-card">
    <div class="pds-card-title"><span class="text-[18px]">纠错工单</span></div>
    <div v-for="t in list" :key="t.id" class="mb-3 rounded-2xl bg-row px-5 py-4">
      <div class="flex items-center gap-2">
        <span class="pds-badge dark">{{ TYPE[t.type] || t.type }}</span>
        <span class="font-medium text-ink">{{ t.question || '（无问题描述）' }}</span>
        <span class="pds-badge" :class="t.status === 'open' ? 'warn' : 'ok'">{{ t.status === 'open' ? '待处理' : t.status }}</span>
        <span class="ml-auto pds-muted">{{ formatTime(t.created_at) }}</span>
      </div>
      <div class="mt-2 text-[13px] text-ink">{{ t.suggestion }}</div>
      <div class="mt-2 flex justify-end"><button v-if="t.status === 'open'" class="pds-btn ghost sm" @click="close(t)">关闭工单</button></div>
    </div>
    <div v-if="!list.length" class="py-16 text-center pds-muted">暂无工单</div>
  </div>
</template>
