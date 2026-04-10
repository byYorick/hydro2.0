<template>
  <section
    v-if="canDiagnose && diagnosticsAvailable"
    class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5"
  >
    <div class="flex items-center justify-between gap-3">
      <div>
        <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">
          Инженерная диагностика
        </h4>
        <p class="text-sm text-[color:var(--text-dim)]">
          Отдельный diagnostics path для dispatcher state и `scheduler_logs`, без влияния на operator contract.
        </p>
      </div>
      <Badge variant="secondary">
        engineer/admin
      </Badge>
    </div>

    <p
      v-if="diagnosticsError"
      class="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700"
    >
      {{ diagnosticsError }}
    </p>

    <div
      v-else-if="diagnosticsLoading && !diagnostics"
      class="mt-4 text-sm text-[color:var(--text-dim)]"
    >
      Загружаем диагностику...
    </div>

    <div
      v-else-if="diagnostics"
      class="mt-4 space-y-4"
    >
      <div class="flex flex-wrap gap-2">
        <Badge variant="info">
          tracked {{ diagnostics.summary.tracked_tasks_total }}
        </Badge>
        <Badge variant="success">
          active {{ diagnostics.summary.active_tasks_total }}
        </Badge>
        <Badge variant="warning">
          overdue {{ diagnostics.summary.overdue_tasks_total }}
        </Badge>
        <Badge variant="danger">
          stale {{ diagnostics.summary.stale_tasks_total }}
        </Badge>
        <Badge variant="secondary">
          logs {{ diagnostics.summary.recent_logs_total }}
        </Badge>
      </div>

      <div class="grid gap-4 xl:grid-cols-2">
        <div class="rounded-xl border border-[color:var(--border-muted)] p-4">
          <div class="flex items-center justify-between gap-3">
            <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Dispatcher tasks
            </h5>
            <span class="text-xs text-[color:var(--text-muted)]">{{ diagnostics.dispatcher_tasks.length }} записей</span>
          </div>
          <div
            v-if="diagnostics.dispatcher_tasks.length === 0"
            class="mt-3 text-sm text-[color:var(--text-dim)]"
          >
            Dispatcher state для зоны пуст.
          </div>
          <div
            v-else
            class="mt-3 space-y-2"
          >
            <div
              v-for="task in diagnostics.dispatcher_tasks"
              :key="task.task_id"
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-3 py-3"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-sm font-semibold text-[color:var(--text-primary)]">{{ task.task_id }}</span>
                <Badge :variant="statusVariant(task.status)">
                  {{ task.status || 'unknown' }}
                </Badge>
                <span class="text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
                  {{ laneLabel(task.task_type) }}
                </span>
              </div>
              <p class="mt-1 text-xs text-[color:var(--text-muted)]">
                {{ task.schedule_key || 'schedule_key не передан' }}
              </p>
              <p class="mt-1 text-xs text-[color:var(--text-dim)]">
                due {{ formatDateTime(task.due_at) }} · poll {{ formatDateTime(task.last_polled_at) }}
              </p>
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] p-4">
          <div class="flex items-center justify-between gap-3">
            <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Scheduler logs
            </h5>
            <span class="text-xs text-[color:var(--text-muted)]">{{ diagnostics.recent_logs.length }} записей</span>
          </div>
          <div
            v-if="diagnostics.recent_logs.length === 0"
            class="mt-3 text-sm text-[color:var(--text-dim)]"
          >
            Исторические scheduler logs для зоны не найдены.
          </div>
          <div
            v-else
            class="mt-3 space-y-2"
          >
            <div
              v-for="log in diagnostics.recent_logs"
              :key="log.log_id"
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-3 py-3"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-sm font-semibold text-[color:var(--text-primary)]">{{ log.task_name || 'scheduler' }}</span>
                <Badge :variant="statusVariant(log.status)">
                  {{ log.status || 'unknown' }}
                </Badge>
              </div>
              <p class="mt-1 text-xs text-[color:var(--text-dim)]">
                {{ formatDateTime(log.created_at) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'

type Diagnostics = {
  summary: {
    tracked_tasks_total: number
    active_tasks_total: number
    overdue_tasks_total: number
    stale_tasks_total: number
    recent_logs_total: number
  }
  dispatcher_tasks: Array<{
    task_id: string
    status?: string | null
    task_type?: string | null
    schedule_key?: string | null
    due_at?: string | null
    last_polled_at?: string | null
  }>
  recent_logs: Array<{
    log_id: number
    task_name?: string | null
    status?: string | null
    created_at?: string | null
  }>
}

defineProps<{
  canDiagnose: boolean
  diagnosticsAvailable: boolean
  diagnosticsLoading: boolean
  diagnosticsError: string | null
  diagnostics: Diagnostics | null

  statusVariant: (status: string) => any
  laneLabel: (taskType: string | null | undefined) => string
  formatDateTime: (value: string | null) => string
}>()
</script>

