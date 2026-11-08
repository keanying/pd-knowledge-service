<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { IconExit } from '@kousum/semi-icons-vue'
import { Modal } from 'view-ui-plus'
import { menuGroups, type MenuGroup, type MenuLeaf } from './menu'
import { useSession } from '@/stores/session'
import { config, logout } from '@/config'

const route = useRoute()
const router = useRouter()
const session = useSession()

const groups = computed(() => menuGroups
  .map((g) => ({ ...g, children: g.children.filter((c) => session.has(...c.perms)) }))
  .filter((g) => g.children.length > 0))
const leafActive = (m: MenuLeaf) =>
  m.path === '/' ? route.path === '/' : [m.path, ...(m.match ?? [])].some((p) => route.path.startsWith(p))
const groupActive = (g: MenuGroup) => g.children.some(leafActive)

const flyout = ref<{ key: string; top: number } | null>(null)
let closeTimer: number | undefined
function openFlyout(g: MenuGroup, e: MouseEvent) {
  window.clearTimeout(closeTimer)
  if (g.children.length < 2) { flyout.value = null; return }
  flyout.value = { key: g.key, top: (e.currentTarget as HTMLElement).getBoundingClientRect().top }
}
function closeFlyout() {
  window.clearTimeout(closeTimer)
  closeTimer = window.setTimeout(() => (flyout.value = null), 160)
}
function keepFlyout() { window.clearTimeout(closeTimer) }
const flyoutGroup = computed(() => groups.value.find((g) => g.key === flyout.value?.key))
function go(path: string) { flyout.value = null; router.push(path) }

// 页面名称显示在浏览器标签页（页面内不重复显示标题）
watch(() => route.meta.title, (t) => { document.title = t ? `${t} - ${config.title}` : config.title }, { immediate: true })

const initial = computed(() => {
  const n = session.me?.user.name || '?'
  return n.length <= 3 ? n.slice(-2) : n.slice(0, 1)
})

function confirmLogout() {
  Modal.confirm({ title: '退出登录', content: '将同时退出统一认证中心，访问其他应用需重新登录。', okText: '退出', onOk: logout })
}
</script>

<template>
  <div class="flex min-h-full gap-5 p-5">
    <aside class="sticky top-5 flex h-[calc(100vh-40px)] w-[76px] shrink-0 flex-col items-center self-start rounded-[38px] bg-ink py-6">
      <button class="mb-8 flex size-11 cursor-pointer items-center justify-center rounded-full border-0 bg-accent text-base font-bold text-ink" :title="config.title" @click="router.push('/')">K</button>
      <nav class="flex flex-1 flex-col items-center gap-3">
        <template v-for="g in groups" :key="g.key">
          <Tooltip v-if="g.children.length === 1" :content="g.title" placement="right" transfer>
            <router-link :to="g.children[0].path" class="flex size-11 items-center justify-center rounded-full transition-colors"
                         :class="groupActive(g) ? 'bg-accent text-ink' : 'text-[#C9CCCB] hover:bg-white/10 hover:text-white'"
                         @mouseenter="openFlyout(g, $event)">
              <component :is="g.icon" />
            </router-link>
          </Tooltip>
          <button v-else class="flex size-11 cursor-pointer items-center justify-center rounded-full border-0 transition-colors"
                  :class="groupActive(g) ? 'bg-accent text-ink' : flyout?.key === g.key ? 'bg-white/10 text-white' : 'bg-transparent text-[#C9CCCB] hover:bg-white/10 hover:text-white'"
                  :aria-label="g.title" @mouseenter="openFlyout(g, $event)" @mouseleave="closeFlyout" @click="go(g.children[0].path)">
            <component :is="g.icon" />
          </button>
        </template>
      </nav>
      <div class="flex flex-col items-center gap-4">
        <Tooltip content="退出登录" placement="right" transfer>
          <button class="flex size-11 cursor-pointer items-center justify-center rounded-full border-0 bg-transparent text-[#C9CCCB] hover:bg-white/10 hover:text-white" @click="confirmLogout">
            <IconExit />
          </button>
        </Tooltip>
        <Tooltip :content="session.me?.user.name" placement="right" transfer>
          <div class="flex size-11 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-ink ring-2 ring-white/20">{{ initial }}</div>
        </Tooltip>
      </div>
    </aside>

    <transition name="flyout">
      <div v-if="flyout && flyoutGroup" class="fixed z-[900] w-[188px] rounded-[20px] bg-white p-2 shadow-[0_12px_32px_rgba(31,36,33,0.16)]"
           :style="{ left: '104px', top: Math.max(16, flyout.top - 8) + 'px' }" @mouseenter="keepFlyout" @mouseleave="closeFlyout">
        <div class="px-3 pb-1 pt-2 text-[12px] text-muted">{{ flyoutGroup.title }}</div>
        <button v-for="c in flyoutGroup.children" :key="c.path"
                class="flex h-10 w-full cursor-pointer items-center justify-between rounded-xl border-0 px-3 text-left text-[14px] transition-colors"
                :class="leafActive(c) ? 'bg-accent font-medium text-ink' : 'bg-transparent text-ink hover:bg-row'" @click="go(c.path)">
          {{ c.title }}<span v-if="c.todo" class="text-[11px] text-muted">建设中</span>
        </button>
      </div>
    </transition>

    <main class="flex min-w-0 flex-1 flex-col">
      <div v-if="session.me?.degraded" class="mb-4 rounded-2xl bg-warn-soft px-4 py-2 text-[13px] text-[#92400E]">
        统一权限服务暂不可用，当前为只读模式（使用缓存的权限），新增与修改操作暂不可用。
      </div>
      <div v-if="session.me?.auth_mode === 'dev'" class="mb-4 rounded-2xl bg-warn-soft px-4 py-2 text-[13px] text-[#92400E]">
        开发模式：未接入 PDS，拥有全部权限，仅限本地调试。
      </div>
      <section class="flex-1 pb-2">
        <router-view />
      </section>
    </main>
  </div>
</template>

<style scoped>
.flyout-enter-active, .flyout-leave-active { transition: opacity .12s, transform .12s; }
.flyout-enter-from, .flyout-leave-to { opacity: 0; transform: translateX(-4px); }
</style>
