<template>
  <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
    <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
      <div>
        <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Ближайшие исполнимые окна</h4>
        <p class="text-sm text-[color:var(--text-dim)]">
          Показываем только окна task types, которые runtime действительно умеет исполнять.
        </p>
      </div>
      <div class="text-xs text-[color:var(--text-muted)]">
        Timezone: {{ timezone || 'UTC' }}
      </div>
    </div>

    <div
      v-if="windows.length === 0"
      class="mt-4 rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
    >
      На выбранном горизонте нет исполнимых окон.
    </div>

    <div
      v-else
      class="mt-4 space-y-2"
    >
      <article
        v-for="(window, index) in windows"
        :key="window.plan_window_id"
        class="relative flex gap-3"
      >
        <div class="relative flex w-4 shrink-0 justify-center">
          <span
            class="mt-2 h-2.5 w-2.5 rounded-full"
            :class="index === 0 ? 'bg-[color:var(--accent-cyan)]' : 'bg-[color:var(--text-muted)]'"
            :title="index === 0 ? 'Следующее окно' : 'Окно'"
          />
          <span
            v-if="index < windows.length - 1"
            class="absolute bottom-0 top-4 w-px bg-[color:var(--border-muted)]"
          />
        </div>

        <div
          class="min-w-0 flex-1 rounded-2xl border bg-[color:var(--surface-card)]/20 px-4 py-3"
          :class="index === 0
            ? 'border-[color:var(--border-strong)] shadow-[0_0_0_1px_color-mix(in_srgb,var(--accent-cyan)_30%,transparent)]'
            : 'border-[color:var(--border-muted)]'"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="text-sm font-semibold text-[color:var(--text-primary)]">
                {{ formatDateTime(window.trigger_at) }}
              </p>
              <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-dim)]">
                <span class="metric-pill">
                  {{ formatRelativeTrigger(window.trigger_at) }}
                </span>
                <Badge variant="success">{{ laneLabel(window.task_type) }}</Badge>
                <span class="metric-pill">
                  mode <span class="text-[color:var(--text-primary)]">{{ window.mode }}</span>
                </span>
                <span
                  v-if="index === 0"
                  class="metric-pill"
                >
                  next
                </span>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>

    <div
      v-if="configOnlyLanes.length > 0"
      class="mt-5 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/15 p-4"
    >
      <p class="text-sm font-semibold text-[color:var(--text-primary)]">Сконфигурировано, но не исполняется этим runtime</p>
      <div class="mt-3 flex flex-wrap gap-2">
        <Badge
          v-for="lane in configOnlyLanes"
          :key="lane.task_type"
          variant="secondary"
        >
          {{ lane.label }}
        </Badge>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'

type ExecutableWindow = {
  plan_window_id: string | number
  trigger_at: string
  task_type: string
  mode: string
}

type ConfigOnlyLane = {
  task_type: string
  label: string
}

defineProps<{
  windows: ExecutableWindow[]
  timezone: string | null | undefined
  configOnlyLanes: ConfigOnlyLane[]
  laneLabel: (taskType: string | null | undefined) => string
  formatDateTime: (value: string | null) => string
  formatRelativeTrigger: (value: string) => string
}>()
</script>

