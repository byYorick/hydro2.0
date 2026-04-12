<template>
  <section class="surface-card rounded-xl border border-[color:var(--border-muted)] p-2 md:p-3">
    <div class="flex items-center justify-between gap-2">
      <h4 class="text-xs font-semibold text-[color:var(--text-primary)]">Ближайшие окна</h4>
      <span class="text-[10px] text-[color:var(--text-muted)]">{{ timezone || 'UTC' }}</span>
    </div>

    <!-- Пусто -->
    <div
      v-if="windows.length === 0"
      class="mt-2 rounded-lg border border-dashed border-[color:var(--border-muted)] px-2.5 py-2 text-xs text-[color:var(--text-dim)]"
    >
      Нет исполнимых окон на горизонте.
    </div>

    <template v-else>
      <!-- Первое окно — акцент -->
      <div class="mt-2 rounded-lg border border-[color:var(--accent-cyan)]/30 bg-[color:var(--accent-cyan)]/5 px-3 py-2">
        <div class="text-[9px] font-semibold uppercase tracking-widest text-[color:var(--accent-cyan)]">
          Следующее
        </div>
        <div class="mt-0.5 text-xl font-bold tabular-nums text-[color:var(--text-primary)]">
          {{ formatRelativeTrigger(windows[0].trigger_at) }}
        </div>
        <div class="mt-1 flex flex-wrap items-center gap-1.5">
          <Badge variant="success" size="sm">{{ laneLabel(windows[0].task_type) }}</Badge>
          <span class="text-[11px] text-[color:var(--text-dim)]">
            {{ formatDateTime(windows[0].trigger_at) }}
          </span>
          <span class="metric-pill text-[10px]">{{ modeLabel(windows[0].mode) }}</span>
        </div>
      </div>

      <!-- Остальные окна — список -->
      <div v-if="windows.length > 1" class="mt-1.5 space-y-1">
        <div
          v-for="w in windows.slice(1)"
          :key="w.plan_window_id"
          class="flex items-center gap-2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/15 px-2.5 py-1.5"
        >
          <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-[color:var(--text-muted)]"></span>
          <Badge variant="secondary" size="sm">{{ laneLabel(w.task_type) }}</Badge>
          <span class="text-[11px] text-[color:var(--text-dim)]">{{ formatRelativeTrigger(w.trigger_at) }}</span>
          <span class="ml-auto text-[10px] text-[color:var(--text-muted)]">{{ formatDateTime(w.trigger_at) }}</span>
        </div>
      </div>
    </template>

    <!-- Config-only lanes -->
    <div
      v-if="configOnlyLanes.length > 0"
      class="mt-2 rounded-md border border-dashed border-[color:var(--border-muted)] px-2.5 py-1.5"
    >
      <p class="text-[10px] text-[color:var(--text-dim)]">Не исполняется runtime:</p>
      <div class="mt-1 flex flex-wrap gap-1">
        <Badge
          v-for="lane in configOnlyLanes"
          :key="lane.task_type"
          variant="secondary"
          size="sm"
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
  modeLabel: (mode: string | null | undefined) => string
  formatDateTime: (value: string | null) => string
  formatRelativeTrigger: (value: string) => string
}>()
</script>
