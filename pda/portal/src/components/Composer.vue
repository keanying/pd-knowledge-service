<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { IconPlus, IconMicrophone, IconArrowUp, IconChevronDown, IconStop } from '@kousum/semi-icons-vue'

/** 输入框：多行、附件（需 pda:chat:upload）、回答模式、语音（规划中）、发送 / 停止。 */
const props = defineProps<{ busy?: boolean; canUpload?: boolean; placeholder?: string; autofocus?: boolean }>()
const emit = defineEmits<{ send: [text: string]; stop: [] }>()
const mode = defineModel<'quick' | 'deep'>('mode', { default: 'quick' })
const text = ref('')
const ta = ref<HTMLTextAreaElement | null>(null)
const modeOpen = ref(false)
const MODES = { quick: ['快速回答', '检索 5 条依据，回答简洁'], deep: ['深度回答', '检索更多依据，回答更完整'] } as const

function grow() {
  const el = ta.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}
watch(text, () => nextTick(grow))
function submit() {
  const t = text.value.trim()
  if (!t || props.busy) return
  emit('send', t)
  text.value = ''
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit() }
}
defineExpose({ focus: () => ta.value?.focus() })
</script>

<template>
  <div class="glass-strong rounded-[22px] px-4 pb-3 pt-3">
    <textarea ref="ta" v-model="text" rows="1" :autofocus="autofocus" :placeholder="placeholder || '有问题，尽管问'"
              class="block max-h-[180px] min-h-[30px] w-full resize-none border-0 bg-transparent px-1 py-1 text-[15px] leading-6 text-ink outline-none placeholder:text-[#9A9EBB]"
              @keydown="onKey" />
    <div class="mt-2 flex items-center gap-2">
      <button class="flex size-9 items-center justify-center rounded-full border border-[#E3E5F0] bg-white text-ink disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="!canUpload" :title="canUpload ? '上传附件（仅本次对话临时解析，不入库）' : '暂无上传附件的权限'"><IconPlus /></button>
      <div class="relative">
        <button class="flex h-9 items-center gap-1 rounded-full border border-[#E3E5F0] bg-white px-3 text-[13px] text-ink" @click="modeOpen = !modeOpen">
          {{ MODES[mode][0] }}<IconChevronDown size="small" />
        </button>
        <div v-if="modeOpen" class="absolute bottom-11 left-0 z-20 w-[220px] rounded-2xl bg-white p-1.5 shadow-[0_12px_32px_rgba(30,34,53,.16)]" @mouseleave="modeOpen = false">
          <button v-for="(v, k) in MODES" :key="k" class="flex w-full flex-col rounded-xl border-0 px-3 py-2 text-left hover:bg-[#F5F6FB]"
                  :class="mode === k ? 'bg-primary-soft' : 'bg-transparent'" @click="mode = k; modeOpen = false">
            <span class="text-[13px] font-medium" :class="mode === k ? 'text-primary' : 'text-ink'">{{ v[0] }}</span>
            <span class="text-[12px] text-muted">{{ v[1] }}</span>
          </button>
        </div>
      </div>
      <div class="flex-1" />
      <button class="flex size-9 cursor-not-allowed items-center justify-center rounded-full border-0 bg-transparent text-muted opacity-60" title="语音输入（规划中）"><IconMicrophone /></button>
      <button v-if="busy" class="flex size-9 items-center justify-center rounded-full border-0 bg-ink text-white" title="停止生成" @click="emit('stop')"><IconStop /></button>
      <button v-else class="flex size-9 items-center justify-center rounded-full border-0 text-white transition-colors"
              :class="text.trim() ? 'bg-primary hover:bg-primary-2' : 'bg-[#C9CBE3]'" :disabled="!text.trim()" title="发送" @click="submit"><IconArrowUp /></button>
    </div>
  </div>
</template>
