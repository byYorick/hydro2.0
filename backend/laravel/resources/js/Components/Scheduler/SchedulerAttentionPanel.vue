<template>
  <section
    v-if="alertItems.length > 0 || statusItems.length > 0"
    class="attention-panel surface-card rounded-2xl border border-[color:var(--border-muted)] p-3"
  >
    <template v-if="alertItems.length > 0">
      <div class="flex items-center justify-between gap-2">
        <h4 class="text-xs font-semibold text-[color:var(--text-primary)]">
          Требует внимания
        </h4>
        <span class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5 text-[10px] text-[color:var(--text-muted)]">
          {{ alertItems.length }}
        </span>
      </div>

      <div class="mt-2 space-y-1.5">
        <AttentionArticle
          v-for="(item, index) in alertItems"
          :key="`alert-${item.title}-${index}`"
          :item="item"
        />
      </div>
    </template>

    <template v-if="statusItems.length > 0">
      <div
        class="flex items-center justify-between gap-2"
        :class="alertItems.length > 0 ? 'mt-4' : ''"
      >
        <h4 class="text-xs font-semibold text-[color:var(--text-primary)]">
          Текущий статус
        </h4>
        <span class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5 text-[10px] text-[color:var(--text-muted)]">
          {{ statusItems.length }}
        </span>
      </div>

      <div class="mt-2 space-y-1.5">
        <AttentionArticle
          v-for="(item, index) in statusItems"
          :key="`status-${item.title}-${index}`"
          :item="item"
        />
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import AttentionArticle, { type AttentionArticleItem } from '@/Components/Scheduler/SchedulerAttentionArticle.vue'

defineProps<{
  alertItems: AttentionArticleItem[]
  statusItems: AttentionArticleItem[]
}>()
</script>

<style scoped>
.attention-panel {
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), var(--shadow-card);
}
</style>
