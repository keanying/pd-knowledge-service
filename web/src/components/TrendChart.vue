<script setup lang="ts">
import { computed } from 'vue'

/** 近 7 日趋势卡（靛蓝底、橙色平滑曲线、最高值所在列高亮）。 */
const props = defineProps<{ title: string; unit: string; points: { label: string; value: number }[] }>()
const W = 300
const H = 120
const coords = computed(() => {
  const max = Math.max(1, ...props.points.map((p) => p.value))
  const n = props.points.length
  return props.points.map((p, i) => ({ x: 18 + (i * (W - 36)) / Math.max(1, n - 1), y: 18 + (1 - p.value / max) * (H - 36), ...p }))
})
// Catmull-Rom → 三次贝塞尔，得到平滑曲线
const path = computed(() => {
  const c = coords.value
  if (!c.length) return ''
  let d = `M${c[0].x},${c[0].y}`
  for (let i = 0; i < c.length - 1; i++) {
    const p0 = c[i - 1] ?? c[i], p1 = c[i], p2 = c[i + 1], p3 = c[i + 2] ?? p2
    d += ` C${p1.x + (p2.x - p0.x) / 6},${p1.y + (p2.y - p0.y) / 6} ${p2.x - (p3.x - p1.x) / 6},${p2.y - (p3.y - p1.y) / 6} ${p2.x},${p2.y}`
  }
  return d
})
const peak = computed(() => coords.value.reduce((a, b) => (b.value > a.value ? b : a), coords.value[0]))
const total = computed(() => props.points.reduce((s, p) => s + p.value, 0))
</script>

<template>
  <div class="rounded-[24px] bg-primary p-5 text-white shadow-[0_12px_28px_rgba(99,102,241,.35)]">
    <div class="flex items-baseline justify-between">
      <span class="text-[14px] font-medium">{{ title }}</span>
      <span class="text-[12px] text-white/70">合计 {{ total }} {{ unit }}</span>
    </div>
    <svg :viewBox="`0 0 ${W} ${H + 22}`" class="mt-2 w-full">
      <rect v-if="peak" :x="peak.x - 18" y="4" width="36" :height="H + 2" rx="14" fill="#fff" opacity=".14" />
      <text v-if="peak" :x="peak.x" y="20" text-anchor="middle" fill="#fff" font-size="13" font-weight="700">{{ peak.value }}</text>
      <path :d="path" stroke="#FF8A5B" stroke-width="3" fill="none" stroke-linecap="round" />
      <circle v-if="peak" :cx="peak.x" :cy="peak.y" r="5" fill="#fff" stroke="#FF8A5B" stroke-width="3" />
      <text v-for="c in coords" :key="c.label" :x="c.x" :y="H + 18" text-anchor="middle" fill="#fff" opacity=".85" font-size="11">{{ c.label }}</text>
    </svg>
  </div>
</template>
