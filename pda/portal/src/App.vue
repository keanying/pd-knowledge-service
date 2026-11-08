<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  IconFile, IconComment, IconAppCenter, IconInfoCircle, IconMore, IconHistory, IconExit, IconPlus,
  IconLikeThumb, IconDislikeThumb, IconCopy, IconRefresh, IconEdit, IconChevronDown, IconChevronUp, IconDelete,
} from '@kousum/semi-icons-vue'
import Composer from './components/Composer.vue'
import Answer from './components/Answer.vue'
import ProcessTimeline, { type Step } from './components/ProcessTimeline.vue'
import { ago, call, chatStream, greeting, type Citation, type Conversation, type Home, type Message } from './api'

const home = ref<Home | null>(null)
const loadError = ref('')
const bg = window.__PDA_CONFIG__?.background
const title = window.__PDA_CONFIG__?.title || '智能助手'

async function loadHome() {
  try { home.value = await call<Home>('GET', '/pda/home') } catch (e: any) { loadError.value = e.message }
}
onMounted(loadHome)

// ---------------- 对话
const view = ref<'home' | 'chat'>('home')
const conv = ref<Conversation | null>(null)
const messages = ref<(Message & { pending?: boolean; progress?: string; error?: string; open?: boolean; plan?: string; steps?: Step[]; elapsed_ms?: number | null })[]>([])
const mode = ref<'quick' | 'deep'>('quick')
const busy = ref(false)
let abort: AbortController | null = null
const scroller = ref<HTMLElement | null>(null)
const scrollDown = () => nextTick(() => scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' }))

async function send(text: string) {
  if (!home.value?.can_chat) return
  view.value = 'chat'
  messages.value.push({ role: 'user', content: text })
  const ans = { role: 'assistant' as const, content: '', citations: [] as Citation[], pending: true, progress: '正在思考…', feedback: null as string | null, open: false, plan: '', steps: [] as Step[], elapsed_ms: null as number | null }
  messages.value.push(ans)
  const msg = messages.value[messages.value.length - 1]
  busy.value = true
  abort = new AbortController()
  scrollDown()
  try {
    await chatStream({ message: text, conversation_id: conv.value?.id, mode: mode.value }, (ev, data) => {
      if (ev === 'meta') conv.value = { id: data.conversation_id, title: conv.value?.title || text.slice(0, 30), updated_at: Date.now() / 1000 }
      else if (ev === 'progress') msg.progress = data.message
      else if (ev === 'plan') { msg.plan = data.text; msg.steps = data.steps; msg.progress = '' }
      else if (ev === 'step') { const k = msg.steps!.findIndex((x) => x.key === data.key); if (k >= 0) msg.steps!.splice(k, 1, data); scrollDown() }
      else if (ev === 'citations') msg.citations = data.items
      else if (ev === 'delta') { msg.content += data.text; msg.progress = ''; scrollDown() }
      else if (ev === 'done') { msg.content = data.text; msg.pending = false; msg.elapsed_ms = data.elapsed_ms }
      else if (ev === 'error') { msg.error = data.message; msg.pending = false }
    }, abort.signal)
  } catch (e: any) {
    if (e.name === 'AbortError') {
      msg.steps?.forEach((x) => { if (x.status === 'running' || x.status === 'pending') x.status = 'skipped' })
      msg.error = '已中止执行'
    } else msg.error = e.message
  } finally {
    msg.pending = false
    busy.value = false
    scrollDown()
  }
}
function stop() { abort?.abort() }
function regenerate(i: number) {
  const q = messages.value[i - 1]?.content
  if (q) send(q)
}

async function openConversation(id: string) {
  const c = await call<Conversation>('GET', `/pda/conversations/${id}`)
  conv.value = c
  messages.value = (c.messages || []).map((m) => ({ ...m }))
  view.value = 'chat'
  historyOpen.value = false
  scrollDown()
}
function newChat() {
  conv.value = null
  messages.value = []
  view.value = 'home'
  historyOpen.value = false
  loadHome()
}

// ---------------- 历史
const historyOpen = ref(false)
const history = ref<Conversation[]>([])
async function openHistory() {
  history.value = await call<Conversation[]>('GET', '/pda/conversations')
  historyOpen.value = true
}
async function removeConversation(id: string) {
  await call('DELETE', `/pda/conversations/${id}`)
  history.value = history.value.filter((c) => c.id !== id)
  if (conv.value?.id === id) newChat()
}

// ---------------- 反馈
const toast = ref('')
function flash(t: string) { toast.value = t; setTimeout(() => (toast.value = ''), 2200) }
const REASONS = ['答非所问', '信息过时', '没有答案', '内容有错误']
const fb = ref<{ index: number; type: 'down' | 'correction'; reason: string; text: string } | null>(null)
async function rate(index: number, rating: 'up' | 'down' | 'correction', reason?: string, correction?: string) {
  if (!conv.value) return
  const r = await call<{ ticket_id?: string }>('POST', '/pda/feedback', { conversation_id: conv.value.id, message_index: index, rating, reason, correction })
  messages.value[index].feedback = rating
  fb.value = null
  flash(rating === 'up' ? '感谢反馈' : r.ticket_id ? '已提交，由知识库负责人处理' : '已记录')
}
async function copy(t: string) { await navigator.clipboard?.writeText(t); flash('已复制') }

// 引用角标 → 展开对应引用
function showCite(m: { citations?: Citation[]; open?: boolean }, n: number) {
  m.open = true
  nextTick(() => document.getElementById(`cite-${messages.value.indexOf(m as any)}-${n}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}

// ---------------- 首页
const firstName = computed(() => home.value?.user.name || '')
const APP_COLORS = ['bg-primary', 'bg-cyan', 'bg-pink', 'bg-blue', 'bg-orange', 'bg-[#22B07D]']
function openApp(a: { homeUrl?: string }) { if (a.homeUrl) window.open(a.homeUrl, '_blank', 'noopener') }
function askDoc(d: { title: string }) { send(`《${d.title}》主要讲了什么？`) }
function logout() { location.href = '/auth/logout' }
</script>

<template>
  <div class="relative min-h-full overflow-hidden" :style="bg ? { backgroundImage: `url(${bg})`, backgroundSize: 'cover', backgroundPosition: 'center' } : {}">
    <!-- 默认背景：靛蓝—薰衣草—暖橙的柔和渐变 -->
    <div v-if="!bg" class="pointer-events-none absolute inset-0 bg-[linear-gradient(160deg,#C9CEFF_0%,#E6E3FF_38%,#F6EEF8_70%,#FFF1E6_100%)]">
      <div class="absolute -left-40 -top-40 size-[520px] rounded-full bg-[#8E92FF] opacity-40 blur-[110px]" />
      <div class="absolute right-[-120px] top-20 size-[420px] rounded-full bg-[#5FD3E0] opacity-25 blur-[110px]" />
      <div class="absolute bottom-[-160px] left-1/3 size-[520px] rounded-full bg-[#FFB48A] opacity-35 blur-[120px]" />
    </div>

    <div class="relative flex h-screen flex-col">
      <!-- 顶栏 -->
      <header class="flex h-16 shrink-0 items-center gap-3 px-6">
        <button class="flex items-center gap-2 border-0 bg-transparent text-[15px] font-semibold text-ink" @click="newChat">
          <img src="/favicon.svg" class="size-8" alt="" />{{ title }}
        </button>
        <div class="flex-1" />
        <button class="glass flex h-9 items-center gap-1.5 rounded-full px-3 text-[13px] text-ink" @click="openHistory"><IconHistory />历史对话</button>
        <button v-if="view === 'chat'" class="glass flex h-9 items-center gap-1.5 rounded-full px-3 text-[13px] text-ink" @click="newChat"><IconPlus />新对话</button>
        <div class="group relative">
          <div class="flex size-9 items-center justify-center rounded-full bg-primary text-[13px] font-semibold text-white">{{ firstName.slice(-2) }}</div>
          <div class="invisible absolute right-0 top-10 z-30 w-44 rounded-2xl bg-white p-2 opacity-0 shadow-[0_12px_32px_rgba(30,34,53,.16)] transition group-hover:visible group-hover:opacity-100">
            <div class="px-3 py-2 text-[13px]"><div class="font-medium">{{ home?.user.name }}</div><div class="text-[12px] text-muted">{{ home?.user.emp_no ? `工号 ${home.user.emp_no}` : '' }}</div></div>
            <button class="flex w-full items-center gap-2 rounded-xl border-0 bg-transparent px-3 py-2 text-left text-[13px] hover:bg-[#F5F6FB]" @click="logout"><IconExit />退出登录</button>
          </div>
        </div>
      </header>

      <div v-if="loadError" class="m-auto rounded-2xl bg-white/80 px-6 py-4 text-[14px]">{{ loadError }}</div>

      <!-- ================= 首页 ================= -->
      <main v-else-if="view === 'home'" class="scroll-thin flex-1 overflow-y-auto px-6 pb-10">
        <div class="mx-auto flex max-w-[1080px] flex-col items-center pt-[8vh]">
          <h1 class="m-0 text-center text-[34px] font-semibold leading-snug text-ink">
            {{ greeting() }}，{{ firstName }}<br /><span class="text-[#3C4066]">今天想了解什么？</span>
          </h1>

          <div v-if="home && !home.can_chat" class="mt-8 rounded-2xl bg-white/80 px-6 py-4 text-center text-[14px]">
            暂无使用智能问答的权限，请联系管理员在 PDS 中申请“使用智能问答”。
          </div>
          <template v-else>
            <div class="mt-8 w-full max-w-[640px]">
              <Composer v-model:mode="mode" :can-upload="home?.can_upload" placeholder="问问知识库，例如：团体票怎么退？" autofocus @send="send" />
            </div>
            <div class="mt-5 flex max-w-[760px] flex-wrap justify-center gap-2.5">
              <button v-for="q in home?.quick_questions" :key="q" class="chip" @click="send(q)">{{ q }}</button>
            </div>
          </template>

          <!-- 三张卡片：最近文档 / 业务应用 / 最近对话 -->
          <div v-if="home" class="mt-[7vh] grid w-full grid-cols-3 gap-5">
            <section class="glass rounded-[24px] p-5">
              <div class="mb-3 flex items-center gap-2 text-[12px] text-[#4B4F70]"><IconFile size="small" />最近引用的文档<span class="flex-1" /><IconInfoCircle size="small" title="对话中引用过的知识文档" /></div>
              <button v-for="d in home.recent_docs" :key="d.doc_id" class="flex w-full items-center gap-3 rounded-xl border-0 bg-transparent px-1 py-2 text-left hover:bg-white/60" @click="askDoc(d)">
                <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white text-primary shadow-sm"><IconFile /></span>
                <span class="min-w-0 flex-1"><span class="block truncate text-[14px] font-medium">{{ d.title }}</span><span class="block text-[12px] text-muted">{{ d.kb_name }} · {{ ago(d.at) }}</span></span>
                <IconMore class="text-muted" />
              </button>
              <div v-if="!home.recent_docs.length" class="py-6 text-center text-[12px] text-muted">提问后，回答引用的文档会出现在这里</div>
            </section>

            <section class="glass rounded-[24px] p-5">
              <div class="mb-3 flex items-center gap-2 text-[12px] text-[#4B4F70]"><IconAppCenter size="small" />我的业务应用<span class="flex-1" /><IconInfoCircle size="small" title="PDS 中本人有权进入的系统，点击单点登录跳转" /></div>
              <div class="grid grid-cols-3 gap-y-4 pt-2">
                <button v-for="(a, i) in home.apps.slice(0, 6)" :key="a.code" class="flex flex-col items-center gap-1.5 border-0 bg-transparent disabled:cursor-not-allowed disabled:opacity-50"
                        :disabled="!a.homeUrl" :title="a.homeUrl ? a.description || a.name : '管理员尚未配置访问地址'" @click="openApp(a)">
                  <span class="flex size-11 items-center justify-center rounded-2xl text-[15px] font-bold text-white shadow-sm" :class="APP_COLORS[i % APP_COLORS.length]">{{ a.name.slice(0, 1) }}</span>
                  <span class="max-w-[90px] truncate text-[12px] text-ink">{{ a.name }}</span>
                </button>
              </div>
              <div v-if="!home.apps.length" class="py-6 text-center text-[12px] text-muted">暂无可进入的业务应用</div>
            </section>

            <section class="glass rounded-[24px] p-5">
              <div class="mb-3 flex items-center gap-2 text-[12px] text-[#4B4F70]"><IconComment size="small" />继续之前的对话<span class="flex-1" /><a class="cursor-pointer text-primary" @click="openHistory">全部</a></div>
              <button v-for="c in home.conversations" :key="c.id" class="flex w-full items-center gap-3 rounded-xl border-0 bg-transparent px-1 py-2 text-left hover:bg-white/60" @click="openConversation(c.id)">
                <span class="flex size-9 shrink-0 items-center justify-center rounded-full bg-white text-ink shadow-sm"><IconComment /></span>
                <span class="min-w-0 flex-1"><span class="block truncate text-[14px] font-medium">{{ c.title }}</span><span class="block text-[12px] text-muted">{{ ago(c.updated_at) }}</span></span>
                <IconMore class="text-muted" />
              </button>
              <div v-if="!home.conversations.length" class="py-6 text-center text-[12px] text-muted">还没有对话</div>
            </section>
          </div>
        </div>
      </main>

      <!-- ================= 对话 ================= -->
      <template v-else>
        <main ref="scroller" class="scroll-thin flex-1 overflow-y-auto px-6">
          <div class="mx-auto flex max-w-[800px] flex-col gap-6 py-6">
            <template v-for="(m, i) in messages" :key="i">
              <div v-if="m.role === 'user'" class="self-end rounded-[20px] rounded-br-md bg-primary px-4 py-2.5 text-[15px] leading-7 text-white shadow-[0_6px_18px_rgba(99,102,241,.25)]">{{ m.content }}</div>
              <div v-else class="glass-strong rounded-[22px] px-6 py-5">
                <div v-if="m.plan" class="mb-3 text-[14px] leading-7 text-[#3C4066]">{{ m.plan }}</div>
                <ProcessTimeline v-if="m.steps?.length" class="mb-4" :steps="m.steps" :running="!!m.pending" :elapsed-ms="m.elapsed_ms" />
                <div v-if="m.progress && !m.content && !m.steps?.length" class="shimmer text-[14px]">{{ m.progress }}</div>
                <Answer v-if="m.content" :text="m.content" @cite="showCite(m, $event)" />
                <span v-if="m.pending && m.content" class="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded bg-primary align-middle" />
                <div v-if="m.error" class="rounded-xl bg-[#FEF2F2] px-3 py-2 text-[13px] text-[#B91C1C]">{{ m.error }}</div>

                <!-- 引用 -->
                <div v-if="m.citations?.length && !m.pending" class="mt-3 border-t border-[#ECEDF6] pt-3">
                  <button class="flex items-center gap-1 border-0 bg-transparent p-0 text-[13px] text-primary" @click="m.open = !m.open">
                    引用 {{ m.citations.length }} 条知识<component :is="m.open ? IconChevronUp : IconChevronDown" size="small" />
                  </button>
                  <div v-if="m.open" class="mt-3 grid gap-2">
                    <div v-for="(c, k) in m.citations" :id="`cite-${i}-${k + 1}`" :key="c.chunk_id" class="rounded-2xl bg-[#F5F6FB] px-4 py-3">
                      <div class="mb-1 flex items-center gap-2 text-[12px] text-muted">
                        <span class="cite">{{ k + 1 }}</span>
                        <span class="font-medium text-ink">{{ c.source.doc_title }}</span>
                        <span>v{{ c.source.version_no }}</span><span v-if="c.source.page_no">· 第 {{ c.source.page_no }} 页</span>
                        <span v-if="c.source.title_path" class="truncate">· {{ c.source.title_path }}</span>
                        <span v-if="c.masked" class="ml-auto rounded-full bg-[#FEF3C7] px-2 text-[11px] text-[#92400E]">已脱敏</span>
                      </div>
                      <Answer class="cite-body" :text="c.text" />
                    </div>
                  </div>
                </div>

                <!-- 操作 -->
                <div v-if="!m.pending && m.content" class="mt-3 flex items-center gap-1 text-muted">
                  <button class="rounded-lg border-0 bg-transparent p-1.5 hover:bg-[#F0F1F8]" :class="m.feedback === 'up' && 'text-primary'" title="有帮助" @click="rate(i, 'up')"><IconLikeThumb /></button>
                  <button class="rounded-lg border-0 bg-transparent p-1.5 hover:bg-[#F0F1F8]" :class="m.feedback === 'down' && 'text-pink'" title="没帮助" @click="fb = { index: i, type: 'down', reason: REASONS[0], text: '' }"><IconDislikeThumb /></button>
                  <button class="rounded-lg border-0 bg-transparent p-1.5 hover:bg-[#F0F1F8]" :class="m.feedback === 'correction' && 'text-orange'" title="纠错" @click="fb = { index: i, type: 'correction', reason: '内容有错误', text: '' }"><IconEdit /></button>
                  <button class="rounded-lg border-0 bg-transparent p-1.5 hover:bg-[#F0F1F8]" title="复制" @click="copy(m.content)"><IconCopy /></button>
                  <button class="rounded-lg border-0 bg-transparent p-1.5 hover:bg-[#F0F1F8]" title="重新生成" :disabled="busy" @click="regenerate(i)"><IconRefresh /></button>
                </div>
              </div>
            </template>
          </div>
        </main>
        <div class="shrink-0 px-6 pb-6 pt-2">
          <div class="mx-auto max-w-[800px]">
            <Composer v-model:mode="mode" :busy="busy" :can-upload="home?.can_upload" placeholder="继续提问…" @send="send" @stop="stop" />
            <div class="mt-2 text-center text-[11px] text-[#7A7F9E]">回答基于企业知识库生成，请以引用原文为准；内容按您的权限检索并已脱敏</div>
          </div>
        </div>
      </template>
    </div>

    <!-- 历史对话抽屉 -->
    <transition name="fade">
      <div v-if="historyOpen" class="fixed inset-0 z-40 bg-[#1E2235]/20" @click.self="historyOpen = false">
        <aside class="absolute bottom-3 left-3 top-3 flex w-[320px] flex-col rounded-[24px] bg-white p-4 shadow-2xl">
          <div class="mb-3 flex items-center justify-between"><span class="text-[15px] font-semibold">历史对话</span>
            <button class="rounded-full border-0 bg-primary px-3 py-1.5 text-[12px] text-white" @click="newChat"><IconPlus size="small" /> 新对话</button></div>
          <div class="scroll-thin flex-1 overflow-y-auto">
            <div v-for="c in history" :key="c.id" class="group flex items-center gap-2 rounded-xl px-2 py-2 hover:bg-[#F5F6FB]" :class="conv?.id === c.id && 'bg-primary-soft'">
              <button class="min-w-0 flex-1 border-0 bg-transparent text-left" @click="openConversation(c.id)">
                <span class="block truncate text-[14px]">{{ c.title }}</span><span class="block text-[12px] text-muted">{{ ago(c.updated_at) }}</span>
              </button>
              <button class="invisible rounded-lg border-0 bg-transparent p-1 text-muted hover:text-pink group-hover:visible" title="删除" @click="removeConversation(c.id)"><IconDelete /></button>
            </div>
            <div v-if="!history.length" class="py-10 text-center text-[13px] text-muted">还没有对话</div>
          </div>
        </aside>
      </div>
    </transition>

    <!-- 点踩 / 纠错 -->
    <div v-if="fb" class="fixed inset-0 z-50 flex items-center justify-center bg-[#1E2235]/25" @click.self="fb = null">
      <div class="w-[440px] rounded-[24px] bg-white p-6 shadow-2xl">
        <div class="text-[16px] font-semibold">{{ fb.type === 'down' ? '哪里不满意？' : '纠正这条回答' }}</div>
        <div class="mt-4 flex flex-wrap gap-2">
          <button v-for="r in REASONS" :key="r" class="chip" :class="fb.reason === r && 'border-primary! bg-primary-soft! text-primary!'" @click="fb.reason = r">{{ r }}</button>
        </div>
        <textarea v-model="fb.text" rows="4" class="mt-4 w-full resize-none rounded-2xl border border-[#E3E5F0] p-3 text-[14px] outline-none focus:border-primary"
                  :placeholder="fb.type === 'correction' ? '请填写正确的内容（必填），将提交给知识库负责人审核' : '补充说明（选填）'" />
        <div class="mt-4 flex justify-end gap-2">
          <button class="h-9 rounded-full border border-[#E3E5F0] bg-white px-4 text-[13px]" @click="fb = null">取消</button>
          <button class="h-9 rounded-full border-0 bg-primary px-4 text-[13px] text-white disabled:opacity-40" :disabled="fb.type === 'correction' && !fb.text.trim()"
                  @click="rate(fb.index, fb.type, fb.reason, fb.text || undefined)">提交</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="fixed left-1/2 top-6 z-[60] -translate-x-1/2 rounded-full bg-ink px-4 py-2 text-[13px] text-white shadow-lg">{{ toast }}</div>
  </div>
</template>

<style scoped>
.cite-body :deep(p) { margin: 0; font-size: 13px; line-height: 1.7; color: #3C4066; }
.cite-body :deep(table) { margin: 4px 0; }
.fade-enter-active, .fade-leave-active { transition: opacity .15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
