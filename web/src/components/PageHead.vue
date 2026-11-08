<script setup lang="ts">
defineProps<{ title: string; sub?: string }>()
</script>

<template>
  <div class="mb-6 flex items-end justify-between gap-4">
    <div>
      <div class="text-[26px] font-bold text-ink">{{ title }}</div>
      <div v-if="sub" class="mt-1 text-[13px] text-muted">{{ sub }}</div>
    </div>
    <div class="flex items-center gap-3"><slot /></div>
  </div>
</template>
