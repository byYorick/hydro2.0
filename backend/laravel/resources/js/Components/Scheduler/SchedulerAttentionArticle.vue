<template>
  <article
    class="relative overflow-hidden rounded-xl border px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
    :class="cardClass(item.tone)"
  >
    <span
      class="absolute left-0 top-0 h-full w-0.5"
      :class="railClass(item.tone)"
    ></span>
    <div class="flex items-start gap-1.5 pl-1.5">
      <span
        class="mt-px shrink-0 text-xs leading-none"
        :class="iconClass(item.tone)"
        aria-hidden="true"
      >
        <span v-if="item.tone === 'danger'">✕</span>
        <span v-else-if="item.tone === 'warning'">!</span>
        <span v-else>i</span>
      </span>
      <div class="min-w-0">
        <p class="text-xs font-medium text-[color:var(--text-primary)]">
          {{ item.title }}
        </p>
        <p
          v-if="item.detail"
          class="mt-0.5 text-[11px] text-[color:var(--text-dim)]"
        >
          {{ item.detail }}
        </p>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
export type AttentionTone = 'danger' | 'warning' | 'info'

export type AttentionArticleItem = {
  title: string
  detail?: string | null
  tone: AttentionTone
}

defineProps<{
  item: AttentionArticleItem
}>()

function cardClass(tone: AttentionTone): string {
  if (tone === 'danger') return 'border-[color:var(--status-critical)] bg-[color:var(--status-critical-soft)]'
  if (tone === 'warning') return 'border-[color:var(--status-warning)] bg-[color:var(--status-warning-soft)]'
  return 'border-[color:var(--status-info)] bg-[color:var(--status-info-soft)]'
}

function railClass(tone: AttentionTone): string {
  if (tone === 'danger') return 'bg-status-critical'
  if (tone === 'warning') return 'bg-status-warning'
  return 'bg-status-info'
}

function iconClass(tone: AttentionTone): string {
  if (tone === 'danger') return 'text-status-critical'
  if (tone === 'warning') return 'text-status-warning'
  return 'text-status-info'
}
</script>
