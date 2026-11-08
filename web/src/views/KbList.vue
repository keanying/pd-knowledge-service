<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHead from '@/components/PageHead.vue'
import { IconPlus, IconSearch, IconBookStroked } from '@kousum/semi-icons-vue'
import { Message } from 'view-ui-plus'
import { api, SECURITY, type Kb } from '@/api'
import { useSession } from '@/stores/session'
import { formatTime } from '@/lib/utils'

const session = useSession()
const router = useRouter()
const list = ref<Kb[]>([])
const keyword = ref('')
const loading = ref(false)
const COLORS = ['bg-primary', 'bg-cyan', 'bg-pink', 'bg-blue', 'bg-orange']
async function load() {
  loading.value = true
  try { list.value = await api.kbs({ keyword: keyword.value || undefined }) } finally { loading.value = false }
}
const route = useRoute()
onMounted(async () => { await load(); if (route.query.create) create() })

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
  <div>
    <PageHead title="知识库" :sub="`共 ${list.length} 个可访问的知识库`">
      <label class="pds-search white w-[260px]"><IconSearch /><input v-model="keyword" placeholder="搜索知识库名称" @keyup.enter="load" /></label>
      <button v-if="session.has('pdk:kb:create')" class="pds-btn dark" @click="create"><IconPlus />新建知识库</button>
    </PageHead>
    <div v-if="!loading && !list.length" class="pds-card py-16 text-center pds-muted">暂无可访问的知识库</div>
    <div class="grid grid-cols-3 gap-5">
      <button v-for="(k, i) in list" :key="k.id" class="cursor-pointer rounded-[24px] border-0 bg-white p-6 text-left transition-shadow hover:shadow-[0_10px_28px_rgba(30,34,53,.08)]" @click="router.push(`/kbs/${k.id}`)">
        <div class="flex items-start gap-4">
          <span class="flex size-12 shrink-0 items-center justify-center rounded-2xl text-white" :class="COLORS[i % COLORS.length]"><IconBookStroked /></span>
          <div class="min-w-0 flex-1">
            <div class="truncate text-[16px] font-semibold text-ink">{{ k.name }}</div>
            <div class="mt-1 flex flex-wrap gap-1.5">
              <span class="pds-badge gray">{{ k.scenic_id === 'GROUP' ? '集团' : '本景区' }}</span>
              <span class="pds-badge gray">{{ SECURITY[k.default_security_level] }}</span>
              <span v-if="k.review_required" class="pds-badge warn">需审核</span>
            </div>
          </div>
        </div>
        <div class="mt-3 line-clamp-2 min-h-[40px] text-[13px] leading-5 text-muted">{{ k.description || '暂无描述' }}</div>
        <div class="mt-4 flex items-center gap-5 border-t border-line pt-4 text-[12px] text-muted">
          <span><b class="text-[16px] text-ink">{{ k.doc_count }}</b> 文档</span>
          <span><b class="text-[16px] text-ink">{{ k.chunk_count }}</b> 切片</span>
          <span class="ml-auto">{{ formatTime(k.updated_at) }}</span>
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
