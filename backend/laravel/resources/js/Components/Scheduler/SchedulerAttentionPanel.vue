<template>
  <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
    <div>
      <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Требует внимания</h4>
      <p class="text-sm text-[color:var(--text-dim)]">
        Короткие сигналы для оператора без raw scheduler timeline.
      </p>
    </div>

    <div
      v-if="items.length === 0"
      class="mt-4 rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
    >
      Критичных сигналов нет.
    </div>

    <div
      v-else
      class="mt-4 space-y-2"
    >
      <article
        v-for="(item, index) in items"
        :key="`${item.title}-${index}`"
        class="relative overflow-hidden rounded-2xl border bg-[color:var(--surface-card)]/25 px-4 py-3"
        :class="attentionCardClass(item.tone)"
      >
        <span
          class="absolute left-0 top-0 h-full w-1"
          :class="toneRailClass(item.tone)"
        />
        <div class="flex items-start gap-3">
          <div
            class="mt-0.5 flex h-7 w-7 items-center justify-center rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 text-sm"
            :class="toneIconClass(item.tone)"
            aria-hidden="true"
          >
            <span v-if="item.tone === 'danger'">✕</span>
            <span v-else-if="item.tone === 'warning'">!</span>
            <span v-else>i</span>
          </div>
          <div class="min-w-0">
        <p class="text-sm font-semibold text-[color:var(--text-primary)]">
          {{ item.title }}
        </p>
        <p
          v-if="item.detail"
          class="mt-1 text-xs text-[color:var(--text-dim)]"
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
  attentionCardClass: (tone: AttentionItem['tone']) => string
}>()

function toneRailClass(tone: AttentionItem['tone']): string {
  if (tone === 'danger') return 'bg-[color:var(--accent-red)]'
  if (tone === 'warning') return 'bg-[color:var(--accent-amber)]'
  return 'bg-[color:var(--accent-cyan)]'
}

function toneIconClass(tone: AttentionItem['tone']): string {
  if (tone === 'danger') return 'text-[color:var(--accent-red)]'
  if (tone === 'warning') return 'text-[color:var(--accent-amber)]'
  return 'text-[color:var(--accent-cyan)]'
}
</script>

