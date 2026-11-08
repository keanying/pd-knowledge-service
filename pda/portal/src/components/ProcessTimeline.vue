<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { IconTick, IconClose, IconSetting, IconChevronDown, IconChevronUp, IconAlertTriangle, IconMore } from '@kousum/semi-icons-vue'

export interface Step {
  key: string; name: string; status: 'pending' | 'running' | 'done' | 'error' | 'skipped'
  detail?: string | null; result?: string | null; warn?: string | null; ms?: number | null
}

/** 执行过程时间线：完成（勾）/ 进行中（旋转）/ 等待（虚线）/ 失败；运行中展开，完成后折叠为摘要，可再展开。 */
const props = defineProps<{ steps: Step[]; running: boolean; elapsedMs?: number | null }>()
const open = ref(props.running)
watch(() => props.running, (r) => { open.value = r })

const done = computed(() => props.steps.filter((s) => s.status === 'done').length)
const failed = computed(() => props.steps.some((s) => s.status === 'error'))
const total = computed(() => props.elapsedMs ?? props.steps.reduce((a, s) => a + (s.ms || 0), 0))
const sec = (ms?: number | null) => (ms == null ? '' : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`)
</script>

<template>
  <div class="rounded-[18px] border border-[#ECEDF6] bg-white/80 px-4 py-3">
    <button class="flex w-full items-center gap-2 border-0 bg-transparent p-0 text-left text-[13px] text-[#4B4F70]" @click="open = !open">
      <IconSetting size="small" :class="running && 'animate-spin [animation-duration:2.5s]'" />
      <span class="font-medium">执行过程</span>
      <span v-if="!running" class="text-muted">· {{ failed ? '未完成' : `已完成 ${done} 步` }} · 用时 {{ sec(total) }}</span>
      <span v-else class="text-primary">· 进行中 {{ done }}/{{ steps.length }}</span>
      <span class="flex-1" />
      <component :is="open ? IconChevronUp : IconChevronDown" size="small" />
    </button>

    <ol v-if="open" class="relative m-0 mt-3 list-none p-0">
      <li v-for="(s, i) in steps" :key="s.key" class="relative flex gap-3 pb-4 last:pb-1">
        <!-- 连接线 -->
        <span v-if="i < steps.length - 1" class="absolute left-[13px] top-[28px] bottom-0 w-px" :class="s.status === 'done' ? 'bg-primary/40' : 'bg-[#E3E5F0]'" />
        <!-- 状态圆点 -->
        <span class="relative z-[1] flex size-[27px] shrink-0 items-center justify-center rounded-full text-white"
              :class="{
                'bg-primary': s.status === 'done',
                'bg-[#EF4444]': s.status === 'error',
                'border-2 border-primary bg-white': s.status === 'running',
                'border-2 border-dashed border-[#C9CBE3] bg-white text-[#B0B3CF]': s.status === 'pending' || s.status === 'skipped',
              }">
          <IconTick v-if="s.status === 'done'" size="small" />
          <IconClose v-else-if="s.status === 'error'" size="small" />
          <span v-else-if="s.status === 'running'" class="size-3.5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <IconMore v-else size="small" />
        </span>
        <div class="min-w-0 flex-1 pt-0.5">
          <div class="flex items-center gap-2">
            <span class="text-[13px] font-medium" :class="{ 'text-primary': s.status === 'running', 'text-[#9A9EBB]': s.status === 'pending' || s.status === 'skipped', 'text-ink': s.status === 'done' || s.status === 'error' }">{{ s.name }}</span>
            <span class="flex-1" />
            <span v-if="s.status === 'done'" class="text-[12px] text-[#22A06B]">✓ {{ sec(s.ms) }}</span>
            <span v-else-if="s.status === 'running'" class="text-[12px] text-primary">进行中…</span>
            <span v-else-if="s.status === 'error'" class="text-[12px] text-[#EF4444]">失败</span>
            <span v-else-if="s.status === 'skipped'" class="text-[12px] text-[#9A9EBB]">已跳过</span>
          </div>
          <div v-if="s.detail" class="mt-0.5 text-[12px] leading-5" :class="s.status === 'pending' ? 'text-[#B0B3CF]' : 'text-muted'">{{ s.detail }}</div>
          <div v-else-if="s.status === 'pending'" class="mt-0.5 text-[12px] text-[#B0B3CF]">等待上一步完成…</div>
          <div v-if="s.result && s.key === 'search'" class="mt-2 rounded-lg bg-[#151827] px-3 py-1.5 font-mono text-[12px] text-[#7EE2A8]">{{ s.result }}</div>
          <div v-else-if="s.result" class="mt-1 text-[12px] text-[#3C4066]">{{ s.result }}</div>
          <div v-if="s.warn" class="mt-2 flex items-center gap-1.5 rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-1.5 text-[12px] text-[#92400E]">
            <IconAlertTriangle size="small" />{{ s.warn }}
          </div>
          <div v-if="s.status === 'running'" class="mt-1.5 flex gap-1"><i v-for="d in 3" :key="d" class="size-1.5 animate-bounce rounded-full bg-[#9A9EBB]" :style="{ animationDelay: `${d * 0.15}s` }" /></div>
        </div>
      </li>
    </ol>
  </div>
</template>
