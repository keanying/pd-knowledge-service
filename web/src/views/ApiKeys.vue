<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { IconPlus } from '@kousum/semi-icons-vue'
import { Message, Modal } from 'view-ui-plus'
import { api, type Kb } from '@/api'
import { formatTime } from '@/lib/utils'

const list = ref<any[]>([])
const kbs = ref<Kb[]>([])
async function load() { list.value = await api.apiKeys() }
onMounted(async () => { await load(); kbs.value = (await api.kbs()).filter((k) => k.my_actions.includes('admin')) })

const open = ref(false)
const form = reactive({ name: '', kb_scope: [] as string[], ip_whitelist: '' })
const secret = ref('')
async function save() {
  if (!form.name.trim()) return Message.warning('请填写名称')
  const r = await api.createApiKey({ name: form.name, kb_scope: form.kb_scope,
    ip_whitelist: form.ip_whitelist.split(/[,，\s]+/).filter(Boolean) })
  open.value = false
  secret.value = r.secret
  await load()
}
function disable(k: any) {
  Modal.confirm({ title: '停用密钥', content: `停用后「${k.name}」将无法调用 PDK 接口`, onOk: async () => { await api.disableApiKey(k.id); await load() } })
}
</script>

<template>
  <div class="pds-card">
    <div class="pds-card-title">
      <span class="text-[18px]">接口密钥</span>
      <button class="pds-btn dark sm" @click="Object.assign(form, { name: '', kb_scope: [], ip_whitelist: '' }); open = true"><IconPlus />创建密钥</button>
    </div>
    <div v-if="secret" class="mb-4 rounded-2xl bg-accent-soft p-4 text-[13px]">
      新密钥（只显示这一次，请立即保存）：<span class="pds-mono select-all font-semibold">{{ secret }}</span>
    </div>
    <table class="w-full border-collapse text-[13px]">
      <thead><tr class="bg-row text-left text-muted">
        <th class="rounded-l-xl px-4 py-3 font-normal">名称</th><th class="px-4 font-normal">前缀</th><th class="px-4 font-normal">知识库范围</th>
        <th class="px-4 font-normal">IP 白名单</th><th class="px-4 font-normal">状态</th><th class="px-4 font-normal">创建时间</th><th class="rounded-r-xl px-4 font-normal">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="k in list" :key="k.id" class="border-b border-line">
          <td class="px-4 py-3 text-ink">{{ k.name }}</td><td class="px-4 pds-mono">{{ k.key_prefix }}…</td>
          <td class="px-4">{{ k.kb_scope.length }} 个</td><td class="px-4">{{ k.ip_whitelist.join('、') || '不限' }}</td>
          <td class="px-4"><span class="pds-dot" :class="k.enabled ? 'ok' : 'off'">{{ k.enabled ? '启用' : '已停用' }}</span></td>
          <td class="px-4 text-muted">{{ formatTime(k.created_at) }}</td>
          <td class="px-4"><a v-if="k.enabled" class="text-danger" @click="disable(k)">停用</a></td>
        </tr>
        <tr v-if="!list.length"><td colspan="7" class="py-12 text-center pds-muted">暂无密钥</td></tr>
      </tbody>
    </table>
    <Modal v-model="open" title="创建接口密钥" :width="520" ok-text="创建" @on-ok="save">
      <Form label-position="top">
        <FormItem label="名称" required><Input v-model="form.name" placeholder="如：客服系统" /></FormItem>
        <FormItem label="可访问的知识库（只能选择本人有管理权的库）">
          <Select v-model="form.kb_scope" multiple><Option v-for="k in kbs" :key="k.id" :value="k.id">{{ k.name }}</Option></Select>
        </FormItem>
        <FormItem label="IP 白名单（逗号分隔，支持网段）"><Input v-model="form.ip_whitelist" placeholder="10.0.0.0/8" /></FormItem>
      </Form>
    </Modal>
  </div>
</template>
