<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <div class="pds-card flex min-h-[360px] flex-col items-center justify-center gap-2 text-center">
    <div class="text-[18px] font-semibold text-ink">{{ route.meta.title }}</div>
    <div class="pds-muted">建设中：功能说明见《PDK 产品功能文档》，界面将按 UX Pilot 设计稿实现。</div>
  </div>
</template>
