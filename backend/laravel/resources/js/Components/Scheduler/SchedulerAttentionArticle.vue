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
  if (tone === 'danger') return 'border-red-200/60 bg-red-50/40 dark:border-red-900/40 dark:bg-red-950/20'
  if (tone === 'warning') return 'border-amber-200/60 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/20'
  return 'border-sky-200/60 bg-sky-50/40 dark:border-sky-900/40 dark:bg-sky-950/20'
}

function railClass(tone: AttentionTone): string {
  if (tone === 'danger') return 'bg-[color:var(--accent-red)]'
  if (tone === 'warning') return 'bg-[color:var(--accent-amber)]'
  return 'bg-[color:var(--accent-cyan)]'
}

function iconClass(tone: AttentionTone): string {
  if (tone === 'danger') return 'text-[color:var(--accent-red)]'
  if (tone === 'warning') return 'text-[color:var(--accent-amber)]'
  return 'text-[color:var(--accent-cyan)]'
}
</script>
