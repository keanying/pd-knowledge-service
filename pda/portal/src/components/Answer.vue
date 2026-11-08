<script setup lang="ts">
import { computed } from 'vue'

/** 回答正文：轻量 Markdown（段落、粗体、有序/无序列表、表格），引用编号 [n] 渲染为可点击角标。先转义再渲染，杜绝注入。 */
const props = defineProps<{ text: string }>()
const emit = defineEmits<{ cite: [n: number] }>()

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function inline(s: string) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\[(\d{1,2})\]/g, '<span class="cite" data-n="$1">$1</span>')
}
const html = computed(() => {
  const out: string[] = []
  const lines = props.text.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i]
    if (/^\s*\|/.test(l)) {
      const rows: string[] = []
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++])
      i--
      const cells = (r: string) => r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      const body = rows.filter((r) => !/^\s*\|[\s:|-]+\|\s*$/.test(r))
      out.push('<table>' + body.map((r, k) => '<tr>' + cells(r).map((c) => (k === 0 ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`)).join('') + '</tr>').join('') + '</table>')
    } else if (/^\s*(\d+[.)、]|[-*])\s+/.test(l)) {
      const ordered = /^\s*\d/.test(l)
      const items: string[] = []
      while (i < lines.length && /^\s*(\d+[.)、]|[-*])\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*(\d+[.)、]|[-*])\s+/, ''))
      i--
      out.push(`<${ordered ? 'ol' : 'ul'}>` + items.map((x) => `<li>${inline(x)}</li>`).join('') + `</${ordered ? 'ol' : 'ul'}>`)
    } else if (l.trim()) {
      out.push(`<p>${inline(l)}</p>`)
    }
  }
  return out.join('')
})
function onClick(e: MouseEvent) {
  const n = (e.target as HTMLElement).dataset.n
  if (n) emit('cite', Number(n))
}
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- 已转义 -->
  <div class="md text-[15px] text-ink" @click="onClick" v-html="html" />
</template>
