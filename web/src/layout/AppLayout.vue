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

function confirmLogout() {
  Modal.confirm({ title: '退出登录', content: '将同时退出统一认证中心，访问其他应用需重新登录。', okText: '退出', onOk: logout })
}
</script>

<template>
  <div class="flex min-h-full gap-6 p-5">
    <!-- 侧栏：靛蓝圆角长条，白色图标；选中为半透明白色圆角方块 -->
    <aside class="sticky top-5 flex h-[calc(100vh-40px)] w-[84px] shrink-0 flex-col items-center self-start rounded-[32px] bg-primary py-7 shadow-[0_10px_30px_rgba(99,102,241,.35)]">
      <button class="mb-9 flex size-12 cursor-pointer items-center justify-center rounded-2xl border-0 bg-white text-[18px] font-bold text-primary" :title="config.title" @click="router.push('/')">K</button>
      <nav class="flex flex-1 flex-col items-center gap-4">
        <template v-for="g in groups" :key="g.key">
          <Tooltip v-if="g.children.length === 1" :content="g.title" placement="right" transfer>
            <router-link :to="g.children[0].path" class="flex size-12 items-center justify-center rounded-2xl text-[18px] transition-colors"
                         :class="groupActive(g) ? 'bg-white/25 text-white' : 'text-white/75 hover:bg-white/15 hover:text-white'"
                         @mouseenter="openFlyout(g, $event)">
              <component :is="g.icon" />
            </router-link>
          </Tooltip>
          <button v-else class="flex size-12 cursor-pointer items-center justify-center rounded-2xl border-0 text-[18px] transition-colors"
                  :class="groupActive(g) || flyout?.key === g.key ? 'bg-white/25 text-white' : 'bg-transparent text-white/75 hover:bg-white/15 hover:text-white'"
                  :aria-label="g.title" @mouseenter="openFlyout(g, $event)" @mouseleave="closeFlyout" @click="go(g.children[0].path)">
            <component :is="g.icon" />
          </button>
        </template>
      </nav>
      <Tooltip content="退出登录" placement="right" transfer>
        <button class="flex size-12 cursor-pointer items-center justify-center rounded-2xl border-0 bg-white/90 text-[18px] text-primary hover:bg-white" @click="confirmLogout">
          <IconExit />
        </button>
      </Tooltip>
    </aside>

    <transition name="flyout">
      <div v-if="flyout && flyoutGroup" class="fixed z-[900] w-[196px] rounded-[20px] bg-white p-2 shadow-[0_12px_32px_rgba(30,34,53,0.16)]"
           :style="{ left: '116px', top: Math.max(16, flyout.top - 8) + 'px' }" @mouseenter="keepFlyout" @mouseleave="closeFlyout">
        <div class="px-3 pb-1 pt-2 text-[12px] text-muted">{{ flyoutGroup.title }}</div>
        <button v-for="c in flyoutGroup.children" :key="c.path"
                class="flex h-10 w-full cursor-pointer items-center justify-between rounded-xl border-0 px-3 text-left text-[14px] transition-colors"
                :class="leafActive(c) ? 'bg-primary font-medium text-white' : 'bg-transparent text-ink hover:bg-row'" @click="go(c.path)">
          {{ c.title }}<span v-if="c.todo" class="text-[11px]" :class="leafActive(c) ? 'text-white/80' : 'text-muted'">建设中</span>
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
