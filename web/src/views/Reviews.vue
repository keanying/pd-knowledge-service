<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Message } from 'view-ui-plus'
import { api } from '@/api'
import { formatTime } from '@/lib/utils'

const list = ref<any[]>([])
async function load() { list.value = await api.reviews() }
onMounted(load)
async function act(r: any, ok: boolean) {
  await (ok ? api.approve(r.version_id) : api.reject(r.version_id))
  Message.success(ok ? '已发布' : '已驳回')
  await load()
}
</script>

<template>
  <div class="pds-card">
    <div class="pds-card-title"><span class="text-[18px]">待我审核（{{ list.length }}）</span></div>
    <div v-for="r in list" :key="r.version_id" class="mb-3 flex items-center gap-4 rounded-2xl bg-row px-5 py-4">
      <div class="flex-1">
        <div class="font-medium text-ink">{{ r.title }} <span class="pds-muted">v{{ r.version_no }}</span></div>
        <div class="pds-muted mt-1">新增 {{ r.stats.added ?? 0 }} · 复用 {{ r.stats.reused ?? 0 }} · 删除 {{ r.stats.removed ?? 0 }} 个切片 · 提交于 {{ formatTime(r.created_at) }}</div>
      </div>
      <button class="pds-btn danger sm" @click="act(r, false)">驳回</button>
      <button class="pds-btn dark sm" @click="act(r, true)">通过并发布</button>
    </div>
    <div v-if="!list.length" class="py-16 text-center pds-muted">没有待审核的内容</div>
  </div>
</template>
