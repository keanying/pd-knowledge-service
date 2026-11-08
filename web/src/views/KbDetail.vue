<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { IconUpload, IconSearch, IconArrowLeft } from '@kousum/semi-icons-vue'
import { Message, Modal } from 'view-ui-plus'
import { api, DOC_STATUS, SECURITY, VERSION_STATUS, type Doc, type Kb, type SearchResult } from '@/api'
import { useSession } from '@/stores/session'
import { formatTime } from '@/lib/utils'

const route = useRoute()
const router = useRouter()
const session = useSession()
const id = computed(() => route.params.id as string)
const kb = ref<Kb | null>(null)
const tab = ref((route.query.tab as string) || 'docs')
const docs = ref<Doc[]>([])
const total = ref(0)
const page = ref(1)

async function loadKb() { kb.value = await api.kb(id.value) }
async function loadDocs() {
  const r = await api.docs({ kb_id: id.value, page: page.value, page_size: 20 })
  docs.value = r.items
  total.value = r.total
}
// 有文档在处理中时轮询刷新状态
let timer: number | undefined
function poll() {
  window.clearTimeout(timer)
  if (docs.value.some((d) => d.latest && !['published', 'failed', 'rejected', 'pending_review', 'superseded'].includes(d.latest.status)))
    timer = window.setTimeout(async () => { await loadDocs(); poll() }, 2000)
  else loadKb()
}
onMounted(async () => { await loadKb(); await loadDocs(); poll() })
onUnmounted(() => window.clearTimeout(timer))

const canWrite = computed(() => kb.value?.my_actions.includes('write'))
const fileInput = ref<HTMLInputElement | null>(null)
async function onFiles(e: Event) {
  const files = Array.from((e.target as HTMLInputElement).files || [])
  let ok = 0
  for (const f of files) {
    const fd = new FormData()
    fd.append('file', f)
    try { await api.upload(id.value, fd); ok++ } catch { /* 失败原因已由拦截器提示 */ }
  }
  if (fileInput.value) fileInput.value.value = ''
  if (ok) Message.success(`已提交 ${ok} 个文件，正在解析`)
  await loadDocs(); poll()
}

function confirm(title: string, content: string, fn: () => Promise<unknown>) {
  Modal.confirm({ title, content, onOk: async () => { await fn(); Message.success('已完成'); await loadDocs() } })
}

// 切片预览
const chunkOpen = ref(false)
const chunkDoc = ref<Doc | null>(null)
const chunks = ref<any[]>([])
async function showChunks(d: Doc) {
  if (!d.latest) return
  chunkDoc.value = d
  chunks.value = (await api.chunks(d.latest.id)).items
  chunkOpen.value = true
}

// 命中测试
const q = ref('')
const result = ref<SearchResult | null>(null)
const searching = ref(false)
async function test() {
  if (!q.value.trim()) return
  searching.value = true
  try { result.value = await api.search({ query: q.value, kb_ids: [id.value], debug: session.has('pdk:search:debug') }) } finally { searching.value = false }
}
</script>

<template>
  <div v-if="kb" class="flex flex-col gap-5">
    <div class="pds-card">
      <div class="flex items-center gap-3">
        <button class="pds-btn ghost sm" @click="router.push('/kbs')"><IconArrowLeft /></button>
        <div class="text-[18px] font-semibold text-ink">{{ kb.name }}</div>
        <span class="pds-badge white">{{ kb.scenic_id === 'GROUP' ? '集团' : kb.scenic_id }}</span>
        <span class="pds-badge gray">默认密级 · {{ SECURITY[kb.default_security_level] }}</span>
        <span class="pds-badge ok">{{ kb.embed_model }}</span>
        <div class="flex-1" />
        <span class="pds-muted">文档 {{ kb.doc_count }} · 切片 {{ kb.chunk_count }}</span>
      </div>
      <div v-if="kb.description" class="mt-2 text-[13px] text-muted">{{ kb.description }}</div>
      <div class="mt-4 flex gap-2">
        <button v-for="t in [['docs', '文档'], ['test', '命中测试']]" :key="t[0]" class="pds-pill" :class="tab === t[0] ? 'bg-ink! text-white!' : ''" @click="tab = t[0]">{{ t[1] }}</button>
      </div>
    </div>

    <div v-if="tab === 'docs'" class="pds-card">
      <div class="pds-card-title">
        <span>文档（{{ total }}）</span>
        <template v-if="canWrite && session.has('pdk:doc:upload')">
          <input ref="fileInput" type="file" multiple class="hidden" @change="onFiles" />
          <button class="pds-btn dark sm" @click="fileInput?.click()"><IconUpload />上传文档</button>
        </template>
      </div>
      <table class="w-full border-collapse text-[13px]">
        <thead><tr class="bg-row text-left text-muted">
          <th class="rounded-l-xl px-4 py-3 font-normal">标题</th><th class="px-4 font-normal">密级</th><th class="px-4 font-normal">状态</th>
          <th class="px-4 font-normal">最新版本</th><th class="px-4 font-normal">更新时间</th><th class="rounded-r-xl px-4 font-normal">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="d in docs" :key="d.id" class="border-b border-line">
            <td class="px-4 py-3"><div class="font-medium text-ink">{{ d.title }}</div><div class="pds-muted">{{ d.file_type.toUpperCase() }} · {{ d.tags.join('、') || '无标签' }}</div></td>
            <td class="px-4">{{ SECURITY[d.security_level] }}</td>
            <td class="px-4"><span class="pds-badge" :class="DOC_STATUS[d.status]?.[1]">{{ DOC_STATUS[d.status]?.[0] || d.status }}</span></td>
            <td class="px-4">
              <template v-if="d.latest">
                v{{ d.latest.version_no }} <span class="pds-badge ml-1" :class="VERSION_STATUS[d.latest.status]?.[1]">{{ VERSION_STATUS[d.latest.status]?.[0] }}</span>
                <div v-if="d.latest.error" class="mt-1 text-[12px] text-danger">{{ d.latest.error }}</div>
                <div v-else-if="d.latest.stats.chunks" class="pds-muted mt-1">切片 {{ d.latest.stats.chunks }}<template v-if="d.latest.stats.reused"> · 复用 {{ d.latest.stats.reused }}</template></div>
              </template>
            </td>
            <td class="px-4 text-muted">{{ formatTime(d.updated_at) }}</td>
            <td class="px-4 whitespace-nowrap">
              <a class="mr-3 text-accent-text" @click="showChunks(d)">切片</a>
              <template v-if="canWrite">
                <a v-if="d.status === 'published'" class="mr-3 text-accent-text" @click="confirm('下线文档', `《${d.title}》将立即停止被检索`, () => api.offline(d.id))">下线</a>
                <a v-if="d.status === 'offline'" class="mr-3 text-accent-text" @click="confirm('重新上线', `《${d.title}》将恢复检索`, () => api.online(d.id))">上线</a>
                <a v-if="session.has('pdk:doc:delete')" class="text-danger" @click="confirm('删除文档', `删除《${d.title}》（30 天内可恢复）`, () => api.deleteDoc(d.id))">删除</a>
              </template>
            </td>
          </tr>
          <tr v-if="!docs.length"><td colspan="6" class="py-12 text-center pds-muted">暂无文档，支持 TXT / MD / CSV；配置 MinerU 后支持 PDF、Word、PPT、Excel 等</td></tr>
        </tbody>
      </table>
      <div v-if="total > 20" class="mt-4 flex justify-end"><Page :total="total" :page-size="20" v-model="page" @on-change="loadDocs" /></div>
    </div>

    <div v-else class="pds-card">
      <div class="flex gap-3">
        <label class="pds-search flex-1"><IconSearch /><input v-model="q" placeholder="输入问题，查看召回与引用（以本人权限检索）" @keyup.enter="test" /></label>
        <button class="pds-btn dark" :disabled="searching" data-test="run-search" @click="test">检索</button>
      </div>
      <div v-if="result" class="mt-5">
        <div class="pds-muted mb-3">命中 {{ result.items.length }} 条 · 耗时 {{ result.latency_ms }}ms<template v-if="result.debug"> · 过滤条件 <span class="pds-mono">{{ result.debug.filter }}</span></template></div>
        <div v-for="(c, i) in result.items" :key="c.chunk_id" class="mb-3 rounded-2xl bg-row p-4">
          <div class="mb-2 flex items-center gap-2 text-[12px] text-muted">
            <span class="pds-badge dark">{{ i + 1 }}</span>
            <span class="font-medium text-ink">{{ c.source.doc_title }}</span>
            <span>v{{ c.source.version_no }}</span><span v-if="c.source.title_path">· {{ c.source.title_path }}</span>
            <span v-if="c.masked" class="pds-badge warn">已脱敏</span>
            <span class="ml-auto pds-mono">{{ c.score.toFixed(4) }}</span>
          </div>
          <div class="whitespace-pre-wrap text-[13px] leading-6 text-ink">{{ c.text }}</div>
        </div>
        <div v-if="!result.items.length" class="py-8 text-center pds-muted">未找到相关内容</div>
      </div>
    </div>

    <Drawer v-model="chunkOpen" :title="`切片 · ${chunkDoc?.title || ''}`" width="640">
      <div v-for="c in chunks" :key="c.id" class="mb-3 rounded-2xl bg-row p-4">
        <div class="mb-1 flex items-center gap-2 text-[12px] text-muted">
          <span>#{{ c.seq }}</span><span class="pds-badge gray">{{ c.chunk_type }}</span>
          <span v-if="c.title_path">{{ c.title_path }}</span>
          <span v-for="p in c.pii_types" :key="p" class="pds-badge warn">{{ p }}</span>
          <span v-if="!c.enabled" class="pds-badge none">已禁用</span>
        </div>
        <div class="whitespace-pre-wrap text-[13px] leading-6">{{ c.content }}</div>
      </div>
    </Drawer>
  </div>
</template>
