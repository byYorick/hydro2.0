<template>
  <section
    v-if="items.length > 0"
    class="attention-panel surface-card rounded-2xl border border-[color:var(--border-muted)] p-3"
  >
    <div class="flex items-center justify-between gap-2">
      <h4 class="text-xs font-semibold text-[color:var(--text-primary)]">
        Требует внимания
      </h4>
      <span class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5 text-[10px] text-[color:var(--text-muted)]">
        {{ items.length }}
      </span>
    </div>

    <div class="mt-2 space-y-1.5">
      <article
        v-for="(item, index) in items"
        :key="`${item.title}-${index}`"
        class="relative overflow-hidden rounded-xl border px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
        :class="cardClass(item.tone)"
      >
        <span
          class="absolute left-0 top-0 h-full w-0.5"
          :class="railClass(item.tone)"
        ></span>
        <div class="flex items-start gap-1.5 pl-1.5">
          <span
            class="mt-px text-xs leading-none shrink-0"
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
    </div>
  </section>
</template>

<script setup lang="ts">
type AttentionItem = {
  title: string
  detail?: string | null
  tone: 'danger' | 'warning' | 'info'
}

defineProps<{
  items: AttentionItem[]
  attentionCardClass?: (tone: AttentionItem['tone']) => string
}>()

function cardClass(tone: AttentionItem['tone']): string {
  if (tone === 'danger') return 'border-red-200/60 bg-red-50/40 dark:border-red-900/40 dark:bg-red-950/20'
  if (tone === 'warning') return 'border-amber-200/60 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/20'
  return 'border-sky-200/60 bg-sky-50/40 dark:border-sky-900/40 dark:bg-sky-950/20'
}

function railClass(tone: AttentionItem['tone']): string {
  if (tone === 'danger') return 'bg-[color:var(--accent-red)]'
  if (tone === 'warning') return 'bg-[color:var(--accent-amber)]'
  return 'bg-[color:var(--accent-cyan)]'
}

function iconClass(tone: AttentionItem['tone']): string {
  if (tone === 'danger') return 'text-[color:var(--accent-red)]'
  if (tone === 'warning') return 'text-[color:var(--accent-amber)]'
  return 'text-[color:var(--accent-cyan)]'
}
</script>

<style scoped>
.attention-panel {
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), var(--shadow-card);
}
</style>
