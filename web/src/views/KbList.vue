<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { IconPlus, IconSearch } from '@kousum/semi-icons-vue'
import { Message } from 'view-ui-plus'
import { api, SECURITY, type Kb } from '@/api'
import { useSession } from '@/stores/session'
import { formatTime } from '@/lib/utils'

const session = useSession()
const router = useRouter()
const list = ref<Kb[]>([])
const keyword = ref('')
const loading = ref(false)
async function load() {
  loading.value = true
  try { list.value = await api.kbs({ keyword: keyword.value || undefined }) } finally { loading.value = false }
}
onMounted(load)

const open = ref(false)
const form = reactive({ name: '', description: '', category: '', scenic_id: '', default_security_level: 1, review_required: false })
function create() {
  Object.assign(form, { name: '', description: '', category: '', scenic_id: session.me?.user.scenic_id || session.me?.scenic_scope[0] || '', default_security_level: Math.min(1, session.me?.max_security_level ?? 0), review_required: false })
  open.value = true
}
async function save() {
  if (!form.name.trim()) return Message.warning('请填写名称')
  const kb = await api.createKb({ ...form, scenic_id: form.scenic_id || undefined })
  open.value = false
  Message.success('已创建')
  router.push(`/kbs/${kb.id}`)
}
</script>

<template>
  <div class="pds-card">
    <div class="mb-5 flex items-center gap-3">
      <div class="text-[18px] font-semibold text-ink">知识库</div>
      <div class="flex-1" />
      <label class="pds-search w-[260px]"><IconSearch /><input v-model="keyword" placeholder="搜索知识库名称" @keyup.enter="load" /></label>
      <button v-if="session.has('pdk:kb:create')" class="pds-btn dark" @click="create"><IconPlus />新建知识库</button>
    </div>
    <div v-if="!loading && !list.length" class="py-16 text-center pds-muted">暂无可访问的知识库</div>
    <div class="grid grid-cols-3 gap-4">
      <button v-for="k in list" :key="k.id" class="cursor-pointer rounded-[20px] border-0 bg-row p-5 text-left transition-colors hover:bg-[#E8EEE3]" @click="router.push(`/kbs/${k.id}`)">
        <div class="flex items-center gap-2">
          <span class="text-[15px] font-semibold text-ink">{{ k.name }}</span>
          <span class="pds-badge white">{{ k.scenic_id === 'GROUP' ? '集团' : k.scenic_id }}</span>
          <span class="pds-badge gray">{{ SECURITY[k.default_security_level] }}</span>
          <span v-if="k.review_required" class="pds-badge warn">需审核</span>
        </div>
        <div class="mt-2 line-clamp-2 min-h-[36px] text-[13px] text-muted">{{ k.description || '—' }}</div>
        <div class="mt-3 flex gap-4 text-[12px] text-muted">
          <span>文档 {{ k.doc_count }}</span><span>切片 {{ k.chunk_count }}</span><span class="ml-auto">{{ formatTime(k.updated_at) }}</span>
        </div>
      </button>
    </div>

    <Modal v-model="open" title="新建知识库" :width="520" @on-ok="save" ok-text="创建" :loading="false">
      <Form label-position="top">
        <FormItem label="名称" required><Input v-model="form.name" maxlength="128" /></FormItem>
        <FormItem label="描述"><Input v-model="form.description" type="textarea" :rows="2" /></FormItem>
        <div class="grid grid-cols-2 gap-4">
          <FormItem label="所属景区">
            <Select v-model="form.scenic_id">
              <Option value="GROUP">集团（共享）</Option>
              <Option v-for="s in session.me?.scenic_scope" :key="s" :value="s">{{ s }}</Option>
            </Select>
          </FormItem>
          <FormItem label="默认密级">
            <Select v-model="form.default_security_level"><Option v-for="(n, i) in SECURITY" :key="i" :value="i" :disabled="i > (session.me?.max_security_level ?? 0)">{{ n }}</Option></Select>
          </FormItem>
        </div>
        <FormItem label="分类"><Input v-model="form.category" placeholder="如：票务、安全应急" /></FormItem>
        <FormItem><Checkbox v-model="form.review_required">新文档与新版本需审核后发布</Checkbox></FormItem>
      </Form>
    </Modal>
  </div>
</template>
