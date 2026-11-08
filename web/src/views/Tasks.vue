<script setup lang="ts">
import PageHead from '@/components/PageHead.vue'
import { onMounted, ref } from 'vue'
import { Message } from 'view-ui-plus'
import { api, TASK_STATUS } from '@/api'
import { useSession } from '@/stores/session'
import { formatTime } from '@/lib/utils'

const session = useSession()
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const status = ref('')
async function load() {
  const r = await api.tasks({ page: page.value, page_size: 20, status: status.value || undefined })
  list.value = r.items
  total.value = r.total
}
onMounted(load)
async function retry(t: any) { await api.retryTask(t.id); Message.success('已重新提交'); await load() }
const STEP: Record<string, string> = { parse: '解析', chunk: '切片', index: '向量化', publish: '发布' }
</script>

<template>
  <div>
    <PageHead title="任务中心" :sub="`共 ${total} 个任务`">
      <Select v-model="status" style="width: 140px" clearable placeholder="全部状态" @on-change="load">
        <Option v-for="(v, k) in TASK_STATUS" :key="k" :value="k">{{ v[0] }}</Option>
      </Select>
    </PageHead>
  <div class="pds-card">
    <table class="w-full border-collapse text-[13px]">
      <thead><tr class="bg-row text-left text-muted">
        <th class="rounded-l-xl px-4 py-3 font-normal">任务</th><th class="px-4 font-normal">状态</th><th class="px-4 font-normal">步骤</th>
        <th class="px-4 font-normal">创建时间</th><th class="px-4 font-normal">失败原因</th><th class="rounded-r-xl px-4 font-normal">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="t in list" :key="t.id" class="border-b border-line">
          <td class="px-4 py-3"><div class="text-ink">{{ t.type === 'ingest' ? '文档接入' : t.type }}</div><div class="pds-mono text-muted">{{ t.ref_id }}</div></td>
          <td class="px-4"><span class="pds-badge" :class="TASK_STATUS[t.status]?.[1]">{{ TASK_STATUS[t.status]?.[0] }}</span></td>
          <td class="px-4">{{ STEP[t.step] || t.step || '—' }}</td>
          <td class="px-4 text-muted">{{ formatTime(t.created_at) }}</td>
          <td class="max-w-[320px] px-4 text-danger">{{ t.error || '' }}</td>
          <td class="px-4"><a v-if="t.status === 'failed' && session.has('pdk:task:manage')" class="text-accent-text" @click="retry(t)">重试</a></td>
        </tr>
        <tr v-if="!list.length"><td colspan="6" class="py-12 text-center pds-muted">暂无任务</td></tr>
      </tbody>
    </table>
    <div v-if="total > 20" class="mt-4 flex justify-end"><Page :total="total" :page-size="20" v-model="page" @on-change="load" /></div>
  </div>
  </div>
</template>
