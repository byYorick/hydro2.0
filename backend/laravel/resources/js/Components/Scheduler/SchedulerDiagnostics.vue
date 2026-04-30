<template>
  <div
    v-if="canDiagnose && diagnosticsAvailable"
    class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden"
  >
    <!-- Аккордеон-заголовок -->
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition-colors hover:bg-[color:var(--surface-card)]/30"
      @click="open = !open"
    >
      <div class="flex items-center gap-1.5">
        <span class="text-xs font-semibold text-[color:var(--text-primary)]">Инженерная диагностика</span>
        <Badge
          variant="secondary"
          size="sm"
        >
          инженер/адм.
        </Badge>
        <div
          v-if="diagnostics"
          class="flex items-center gap-1"
        >
          <Badge
            v-if="diagnostics.summary.overdue_tasks_total > 0"
            variant="warning"
            size="sm"
          >
            просрочено {{ diagnostics.summary.overdue_tasks_total }}
          </Badge>
          <Badge
            v-if="diagnostics.summary.stale_tasks_total > 0"
            variant="danger"
            size="sm"
          >
            устарело {{ diagnostics.summary.stale_tasks_total }}
          </Badge>
        </div>
      </div>
      <svg
        class="h-3.5 w-3.5 shrink-0 text-[color:var(--text-dim)] transition-transform duration-200"
        :class="open ? 'rotate-180' : ''"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
      >
        <path
          d="M4 6l4 4 4-4"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <!-- Тело аккордеона -->
    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      enter-from-class="opacity-0 max-h-0"
      enter-to-class="opacity-100 max-h-[2000px]"
      leave-active-class="transition-all duration-150 ease-in"
      leave-from-class="opacity-100 max-h-[2000px]"
      leave-to-class="opacity-0 max-h-0"
    >
      <div
        v-if="open"
        class="border-t border-[color:var(--border-muted)] p-2 md:p-3 space-y-2"
      >
        <p
          v-if="diagnosticsError"
          class="rounded-md border border-amber-200/60 bg-amber-50/40 px-2.5 py-1.5 text-[11px] text-amber-700 dark:border-amber-800/40 dark:bg-amber-950/20 dark:text-amber-400"
        >
          {{ diagnosticsError }}
        </p>

        <div
          v-else-if="diagnosticsLoading && !diagnostics"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Загружаем диагностику...
        </div>

        <template v-else-if="diagnostics">
          <!-- Счётчики -->
          <div class="flex flex-wrap gap-1">
            <Badge
              variant="info"
              size="sm"
            >
              отслеживается {{ diagnostics.summary.tracked_tasks_total }}
            </Badge>
            <Badge
              variant="success"
              size="sm"
            >
              активно {{ diagnostics.summary.active_tasks_total }}
            </Badge>
            <Badge
              variant="warning"
              size="sm"
            >
              просрочено {{ diagnostics.summary.overdue_tasks_total }}
            </Badge>
            <Badge
              variant="danger"
              size="sm"
            >
              устарело {{ diagnostics.summary.stale_tasks_total }}
            </Badge>
            <Badge
              variant="secondary"
              size="sm"
            >
              логи {{ diagnostics.summary.recent_logs_total }}
            </Badge>
          </div>

          <div class="grid gap-2 xl:grid-cols-2">
            <!-- Задачи dispatcher -->
            <div class="rounded-lg border border-[color:var(--border-muted)] p-2">
              <div class="flex items-center justify-between gap-2 mb-1.5">
                <h5 class="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
                  Задачи диспетчера
                </h5>
                <span class="text-[10px] text-[color:var(--text-muted)]">{{ diagnostics.dispatcher_tasks.length }}</span>
              </div>
              <div
                v-if="diagnostics.dispatcher_tasks.length === 0"
                class="text-[11px] text-[color:var(--text-dim)]"
              >
                Пусто.
              </div>
              <div
                v-else
                class="space-y-1"
              >
                <div
                  v-for="task in diagnostics.dispatcher_tasks"
                  :key="task.task_id"
                  class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-2 py-1.5"
                >
                  <div class="flex flex-wrap items-center gap-1">
                    <span class="font-mono text-[11px] font-semibold text-[color:var(--text-primary)]">{{ task.task_id }}</span>
                    <Badge
                      :variant="statusVariant(task.status)"
                      size="sm"
                    >
                      {{ statusLabel(task.status) }}
                    </Badge>
                    <span class="text-[10px] text-[color:var(--text-dim)]">{{ laneLabel(task.task_type) }}</span>
                  </div>
                  <p class="mt-0.5 text-[10px] text-[color:var(--text-muted)]">
                    {{ task.schedule_key ?? '—' }}
                  </p>
                  <p class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">
                    срок {{ formatDateTime(task.due_at) }} · опрос {{ formatDateTime(task.last_polled_at) }}
                  </p>
                </div>
              </div>
            </div>

            <!-- Логи планировщика -->
            <div class="rounded-lg border border-[color:var(--border-muted)] p-2">
              <div class="flex items-center justify-between gap-2 mb-1.5">
                <h5 class="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-dim)]">
                  Логи планировщика
                </h5>
                <span class="text-[10px] text-[color:var(--text-muted)]">{{ diagnostics.recent_logs.length }}</span>
              </div>
              <div
                v-if="diagnostics.recent_logs.length === 0"
                class="text-[11px] text-[color:var(--text-dim)]"
              >
                Пусто.
              </div>
              <div
                v-else
                class="space-y-1"
              >
                <div
                  v-for="log in diagnostics.recent_logs"
                  :key="log.log_id"
                  class="flex items-center justify-between gap-2 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/20 px-2 py-1.5"
                >
                  <div class="flex items-center gap-1 min-w-0">
                    <span class="font-mono text-[11px] font-semibold text-[color:var(--text-primary)] truncate">
                      {{ log.task_name ?? 'планировщик' }}
                    </span>
                    <Badge
                      :variant="statusVariant(log.status)"
                      size="sm"
                    >
                      {{ statusLabel(log.status) }}
                    </Badge>
                  </div>
                  <span class="text-[10px] text-[color:var(--text-muted)] shrink-0">
                    {{ formatDateTime(log.created_at) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
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
  statusLabel: (status: string | null | undefined) => string
  laneLabel: (taskType: string | null | undefined) => string
  formatDateTime: (value: string | null) => string
}>()

const open = ref(false)
</script>
