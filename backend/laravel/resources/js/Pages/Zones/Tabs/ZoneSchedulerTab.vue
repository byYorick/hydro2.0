<template>
  <div class="space-y-6">
    <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
              Планировщик зоны #{{ zoneId }}
            </span>
            <span class="h-1 w-1 rounded-full bg-[color:var(--text-muted)]"></span>
            <span class="text-[11px] font-semibold text-[color:var(--text-dim)]">{{ todayLabel }}</span>
            <Badge variant="info">Live sync</Badge>
            <Badge :variant="controlModeBadgeVariant">{{ automationControlModeLabel }}</Badge>
          </div>
          <h3 class="mt-2 font-headline text-2xl font-bold tracking-tight text-[color:var(--text-primary)]">
            Linear-style план задач
          </h3>
          <p class="mt-1 text-sm text-[color:var(--text-dim)]">
            Плотный список задач слева, шаги и детали выбранной задачи справа.
          </p>
        </div>

        <div class="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            :disabled="schedulerTaskListLoading"
            @click="refreshSchedulerState"
          >
            {{ schedulerTaskListLoading ? 'Обновляем...' : 'Обновить' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!latestRecentTaskId"
            @click="openLatestRecentTask"
          >
            Открыть текущую
          </Button>
        </div>
      </div>

      <p
        v-if="schedulerTaskError"
        class="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        {{ schedulerTaskError }}
      </p>
    </section>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)]">
      <section class="surface-card surface-card--elevated overflow-hidden rounded-[1.5rem] border border-[color:var(--border-muted)]">
        <div class="border-b border-[color:var(--border-muted)] px-4 py-4 md:px-5">
          <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Лента задач</h4>
              <p class="text-sm text-[color:var(--text-dim)]">Текущие, будущие и недавние записи в одном плотном списке.</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <Badge variant="warning">Активно {{ taskSummary.active }}</Badge>
              <Badge variant="secondary">Ожидают {{ futureSchedulerTasks.length }}</Badge>
              <Badge variant="success">Завершено {{ taskSummary.done }}</Badge>
            </div>
          </div>

          <div class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_150px_120px_auto]">
            <input
              :value="schedulerTaskSearch"
              type="text"
              class="input-field"
              placeholder="Поиск: ID, статус, причина"
              @input="onSchedulerTaskSearchInput"
            />
            <select
              :value="schedulerTaskPreset"
              class="input-select"
              @change="onSchedulerTaskPresetChange"
            >
              <option
                v-for="preset in schedulerTaskPresetOptions"
                :key="preset.value"
                :value="preset.value"
              >
                {{ preset.label }}
              </option>
            </select>
            <Button
              size="sm"
              variant="outline"
              :disabled="schedulerTaskListLoading"
              @click="fetchRecentSchedulerTasks"
            >
              {{ schedulerTaskListLoading ? '...' : 'Обновить' }}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              @click="resetTaskFilters"
            >
              Сбросить
            </Button>
          </div>
        </div>

        <div class="max-h-[960px] overflow-y-auto">
          <div
            v-if="timelineTaskGroups.length === 0"
            class="px-4 py-6 text-sm text-[color:var(--text-dim)] md:px-5"
          >
            Задачи не найдены.
          </div>

          <div
            v-for="group in timelineTaskGroups"
            :key="group.key"
            class="border-b border-[color:var(--border-muted)] last:border-0"
          >
            <div class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--text-dim)] md:px-5">
              {{ group.label }}
            </div>

            <button
              v-for="task in group.tasks"
              :key="task.task_id"
              type="button"
              class="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-[color:var(--surface-card)]/35 md:px-5"
              :class="task.task_id === latestRecentTaskId ? 'bg-[color:var(--surface-card)]/45' : ''"
              @click="lookupSchedulerTask(task.task_id)"
            >
              <div
                class="mt-1 h-2.5 w-2.5 shrink-0 rounded-full"
                :class="timelineDotClass(resolveTaskTone(task.status))"
              ></div>

              <div class="min-w-0 flex-1">
                <div class="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="font-mono text-sm font-semibold text-[color:var(--text-primary)]">
                        #{{ task.task_id }}
                      </span>
                      <Badge :variant="schedulerTaskStatusVariant(task.status)">
                        {{ schedulerTaskStatusLabel(task.status) }}
                      </Badge>
                      <span class="text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
                        {{ schedulerTaskTypeLabel(task.task_type) }}
                      </span>
                    </div>
                    <p class="mt-1 truncate text-sm text-[color:var(--text-primary)]">
                      {{ compactTaskSubtitle(task) }}
                    </p>
                    <p class="mt-1 text-xs text-[color:var(--text-muted)]">
                      {{ task.updated_at ? formatDateTime(task.updated_at) : 'Время не передано' }}
                    </p>
                  </div>

                  <span class="shrink-0 text-xs text-[color:var(--text-dim)]">
                    {{ compactTaskMeta(task) }}
                  </span>
                </div>
              </div>
            </button>
          </div>
        </div>
      </section>

      <div class="space-y-6">
        <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
          <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-sm font-semibold text-[color:var(--text-primary)]">
                  {{ latestRecentTask ? `#${latestRecentTask.task_id}` : '#—' }}
                </span>
                <Badge :variant="latestRecentTask ? schedulerTaskStatusVariant(latestRecentTask.status) : 'secondary'">
                  {{ latestRecentTask ? schedulerTaskStatusLabel(latestRecentTask.status) : 'Нет данных' }}
                </Badge>
                <span class="text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
                  {{ latestRecentTask ? schedulerTaskTypeLabel(latestRecentTask.task_type) : 'Ожидание' }}
                </span>
              </div>
              <h4 class="mt-2 font-headline text-xl font-bold text-[color:var(--text-primary)]">
                Шаги выполнения
              </h4>
              <p class="mt-1 text-sm text-[color:var(--text-dim)]">
                {{ latestRecentTask ? compactTaskSubtitle(latestRecentTask) : 'Выберите задачу из ленты слева.' }}
              </p>
            </div>

            <div class="text-right text-xs text-[color:var(--text-muted)]">
              <div>Sync: {{ schedulerTasksUpdatedAt ? formatDateTime(schedulerTasksUpdatedAt) : '—' }}</div>
              <div class="mt-1">Активно {{ taskSummary.active }} / Всего {{ taskSummary.total }}</div>
            </div>
          </div>

          <div class="mt-5 space-y-3">
            <div
              v-for="step in executionSteps"
              :key="step.id"
              class="flex gap-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 px-4 py-3"
            >
              <div class="flex w-7 shrink-0 flex-col items-center">
                <div
                  class="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold text-white"
                  :class="timelineDotClass(step.tone)"
                >
                  {{ step.index }}
                </div>
                <div
                  v-if="step.index !== executionSteps.length"
                  class="mt-1 h-full w-px bg-[color:var(--border-muted)]"
                ></div>
              </div>

              <div class="min-w-0 flex-1">
                <div class="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                  <p class="text-sm font-semibold text-[color:var(--text-primary)]">{{ step.title }}</p>
                  <span class="text-xs text-[color:var(--text-muted)]">{{ step.timeLabel }}</span>
                </div>
                <p class="mt-1 text-xs text-[color:var(--text-dim)]">{{ step.subtitle }}</p>
                <div class="mt-2">
                  <Badge :variant="step.badgeVariant">{{ step.badgeText }}</Badge>
                </div>
              </div>
            </div>

            <div
              v-if="executionSteps.length === 0"
              class="rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
            >
              Шаги выполнения пока недоступны.
            </div>
          </div>
        </section>

        <section class="surface-card surface-card--elevated rounded-[1.5rem] border border-[color:var(--border-muted)] p-4 md:p-5">
          <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <h4 class="font-headline text-lg font-bold text-[color:var(--text-primary)]">Контекст</h4>
              <p class="text-sm text-[color:var(--text-dim)]">Короткая сводка по режиму, телеметрии и деталям выбранной задачи.</p>
            </div>
            <Button
              size="sm"
              variant="ghost"
              :disabled="schedulerTaskLookupLoading"
              @click="fetchAutomationControlMode"
            >
              Синхронизировать режим
            </Button>
          </div>

          <div class="mt-4 grid gap-3 md:grid-cols-2">
            <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4">
              <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Режим</p>
              <p class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{{ automationControlModeLabel }}</p>
            </div>
            <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4">
              <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Ошибки</p>
              <p class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{{ taskSummary.failed }}</p>
            </div>
          </div>

          <div class="mt-4 flex flex-wrap gap-2">
            <span
              v-for="chip in telemetryChips"
              :key="chip.label"
              class="rounded-full border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 px-3 py-1 text-[11px] font-semibold text-[color:var(--text-primary)]"
            >
              {{ chip.label }}: {{ chip.value }}
            </span>
            <span
              v-if="telemetryChips.length === 0"
              class="text-sm text-[color:var(--text-dim)]"
            >
              Телеметрия не передана.
            </span>
          </div>

          <div
            v-if="manualStepPills.length > 0"
            class="mt-4 flex flex-wrap gap-2"
          >
            <span
              v-for="item in manualStepPills"
              :key="item.step"
              class="rounded-full border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 px-3 py-1 text-[11px] text-[color:var(--text-dim)]"
            >
              {{ item.label }}
            </span>
          </div>

          <div class="mt-5">
            <ZoneAutomationSchedulerTaskDetailsCard
              v-if="schedulerTaskStatus"
              :scheduler-task-status="schedulerTaskStatus"
              :scheduler-task-sla="schedulerTaskSla"
              :scheduler-task-done="schedulerTaskDone"
              :scheduler-task-timeline="schedulerTaskTimeline"
              :format-date-time="formatDateTime"
              :scheduler-task-status-variant="schedulerTaskStatusVariant"
              :scheduler-task-status-label="schedulerTaskStatusLabel"
              :scheduler-task-type-label="schedulerTaskTypeLabel"
              :scheduler-task-decision-label="schedulerTaskDecisionLabel"
              :scheduler-task-reason-label="schedulerTaskReasonLabel"
              :scheduler-task-error-label="schedulerTaskErrorLabel"
              :scheduler-task-process-status-variant="schedulerTaskProcessStatusVariant"
              :scheduler-task-process-status-label="schedulerTaskProcessStatusLabel"
              :scheduler-task-event-label="schedulerTaskEventLabel"
              :scheduler-task-timeline-step-label="schedulerTaskTimelineStepLabel"
              :scheduler-task-timeline-stage-label="schedulerTaskTimelineStageLabel"
            />
            <div
              v-else
              class="rounded-xl border border-dashed border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-4 text-sm text-[color:var(--text-dim)]"
            >
              Детали появятся после выбора задачи.
            </div>
          </div>
        </section>
      </div>
    </div>

    <details class="surface-card surface-card--elevated group rounded-2xl border border-[color:var(--border-muted)]">
      <summary class="cursor-pointer list-none px-5 py-4 flex items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium text-[color:var(--text-primary)]">
            Диагностика scheduler
          </span>
          <Badge variant="secondary">
            dev
          </Badge>
        </div>
        <span class="text-xs text-[color:var(--text-dim)] group-open:hidden">
          открыть панель
        </span>
        <span class="text-xs text-[color:var(--text-dim)] hidden group-open:inline">
          скрыть панель
        </span>
      </summary>

      <div class="border-t border-[color:var(--border-muted)] p-4 md:p-5">
        <AutomationSchedulerDevCard
          :scheduler-task-id-input="schedulerTaskIdInput"
          :scheduler-task-lookup-loading="schedulerTaskLookupLoading"
          :scheduler-task-list-loading="schedulerTaskListLoading"
          :scheduler-task-error="schedulerTaskError"
          :scheduler-task-status="schedulerTaskStatus"
          :scheduler-task-sla="schedulerTaskSla"
          :scheduler-task-done="schedulerTaskDone"
          :scheduler-task-timeline="schedulerTaskTimeline"
          :format-date-time="formatDateTime"
          :scheduler-task-status-variant="schedulerTaskStatusVariant"
          :scheduler-task-status-label="schedulerTaskStatusLabel"
          :scheduler-task-type-label="schedulerTaskTypeLabel"
          :scheduler-task-decision-label="schedulerTaskDecisionLabel"
          :scheduler-task-reason-label="schedulerTaskReasonLabel"
          :scheduler-task-error-label="schedulerTaskErrorLabel"
          :scheduler-task-process-status-variant="schedulerTaskProcessStatusVariant"
          :scheduler-task-process-status-label="schedulerTaskProcessStatusLabel"
          :scheduler-task-event-label="schedulerTaskEventLabel"
          :scheduler-task-timeline-step-label="schedulerTaskTimelineStepLabel"
          :scheduler-task-timeline-stage-label="schedulerTaskTimelineStageLabel"
          :filtered-recent-scheduler-tasks="filteredRecentSchedulerTasks"
          :scheduler-task-search="schedulerTaskSearch"
          :scheduler-task-preset="schedulerTaskPreset"
          :scheduler-task-preset-options="schedulerTaskPresetOptions"
          :scheduler-tasks-updated-at="schedulerTasksUpdatedAt"
          @lookup-task="lookupSchedulerTask"
          @refresh-list="fetchRecentSchedulerTasks"
          @update:scheduler-task-id-input="onSchedulerTaskIdInputUpdate"
          @update:scheduler-task-search="onSchedulerTaskSearchUpdate"
          @update:scheduler-task-preset="onSchedulerTaskPresetUpdate"
        />
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import AutomationSchedulerDevCard from '@/Components/AutomationSchedulerDevCard.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import ZoneAutomationSchedulerTaskDetailsCard from '@/Pages/Zones/Tabs/ZoneAutomationSchedulerTaskDetailsCard.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useZoneAutomationScheduler } from '@/composables/useZoneAutomationScheduler'
import type {
  SchedulerTaskStatus,
  SchedulerTaskTimelineItem,
  ZoneAutomationTabProps,
} from '@/composables/zoneAutomationTypes'
import type { AutomationManualStep } from '@/types/Automation'

const props = defineProps<ZoneAutomationTabProps>()

const { showToast } = useToast()
const { get, post } = useApi(showToast)
const scheduler = useZoneAutomationScheduler(props, { get, post, showToast })
const zoneId = computed(() => props.zoneId)

const {
  schedulerTaskIdInput,
  schedulerTaskLookupLoading,
  schedulerTaskListLoading,
  schedulerTaskError,
  schedulerTaskStatus,
  automationControlMode,
  allowedManualSteps,
  recentSchedulerTasks,
  filteredRecentSchedulerTasks,
  schedulerTaskSearch,
  schedulerTaskPreset,
  schedulerTaskPresetOptions,
  schedulerTasksUpdatedAt,
  fetchRecentSchedulerTasks,
  fetchAutomationControlMode,
  lookupSchedulerTask,
  clearSchedulerTasksPollTimer,
  hasActiveSchedulerTask,
  scheduleSchedulerTasksPoll,
  handleVisibilityChange,
  resetForZoneChange,
  schedulerTaskStatusVariant,
  schedulerTaskStatusLabel,
  schedulerTaskTypeLabel,
  schedulerTaskProcessStatusVariant,
  schedulerTaskProcessStatusLabel,
  schedulerTaskEventLabel,
  schedulerTaskTimelineStageLabel,
  schedulerTaskTimelineStepLabel,
  schedulerTaskTimelineItems,
  schedulerTaskDecisionLabel,
  schedulerTaskReasonLabel,
  schedulerTaskErrorLabel,
  schedulerTaskSlaMeta,
  schedulerTaskDoneMeta,
  formatDateTime,
} = scheduler

const schedulerTaskSla = computed(() => schedulerTaskSlaMeta(schedulerTaskStatus.value))
const schedulerTaskDone = computed(() => schedulerTaskDoneMeta(schedulerTaskStatus.value))
const schedulerTaskTimeline = computed(() => schedulerTaskTimelineItems(schedulerTaskStatus.value))
type TimelineTone = 'running' | 'waiting' | 'done' | 'failed'

interface TimelineEntry {
  id: string
  taskId: string | null
  tone: TimelineTone
  icon: string
  timeLabel: string
  statusLabel: string
  kindLabel: string
  title: string
  subtitle: string
  badgeText: string
  badgeVariant: 'success' | 'warning' | 'danger' | 'info' | 'secondary'
  progress: number
}

interface ExecutionStep {
  id: string
  index: number
  tone: TimelineTone
  title: string
  subtitle: string
  timeLabel: string
  badgeText: string
  badgeVariant: 'success' | 'warning' | 'danger' | 'info' | 'secondary'
}

interface TimelineTaskGroup {
  key: string
  label: string
  tasks: SchedulerTaskStatus[]
}

const latestRecentTask = computed(() => {
  const activeTask = recentSchedulerTasks.value.find((task) => isActiveSchedulerTask(task.status))
  return schedulerTaskStatus.value ?? activeTask ?? recentSchedulerTasks.value[0] ?? null
})

const latestRecentTaskId = computed(() => latestRecentTask.value?.task_id?.trim() ?? '')

const taskSummary = computed(() => {
  const summary = {
    total: recentSchedulerTasks.value.length,
    active: 0,
    waiting: 0,
    done: 0,
    failed: 0,
  }

  for (const task of recentSchedulerTasks.value) {
    const bucket = classifySchedulerTaskStatus(task.status)
    summary[bucket] += 1
  }

  return summary
})

const automationControlModeLabel = computed(() => {
  if (automationControlMode.value === 'manual') return 'ручной'
  if (automationControlMode.value === 'semi') return 'полуавто'
  return 'авто'
})

const todayLabel = computed(() => {
  return new Intl.DateTimeFormat('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(new Date())
})

const controlModeBadgeVariant = computed(() => {
  if (automationControlMode.value === 'manual') return 'warning'
  if (automationControlMode.value === 'semi') return 'info'
  return 'success'
})

const manualStepPills = computed(() => {
  return allowedManualSteps.value.map((step) => ({
    step,
    label: formatManualStepLabel(step),
  }))
})

const schedulerPresetCards = computed(() => {
  return schedulerTaskPresetOptions.map((preset) => ({
    value: preset.value,
    label: preset.label,
    icon: presetIcon(preset.value),
    description: presetDescription(preset.value),
    isActive: schedulerTaskPreset.value === preset.value,
  }))
})

const telemetryChips = computed(() => {
  const values = [
    { label: 'pH', value: formatTelemetryMetric(props.telemetry?.ph, 1) },
    { label: 'EC', value: formatTelemetryMetric(props.telemetry?.ec, 1) },
    { label: 'Темп.', value: formatTelemetryMetric(props.telemetry?.temperature, 1, '°C') },
    { label: 'Влажн.', value: formatTelemetryMetric(props.telemetry?.humidity, 0, '%') },
  ]

  return values.filter((item) => item.value !== null).map((item) => ({
    label: item.label,
    value: item.value as string,
  }))
})

const statusHeroTitle = computed(() => {
  if (taskSummary.value.failed > 0) return 'Требует внимания'
  if (taskSummary.value.active > 0) return 'Оптимальный ритм'
  if (taskSummary.value.done > 0) return 'Цикл стабилен'
  return 'Ожидание задач'
})

const statusHeroDescription = computed(() => {
  if (taskSummary.value.failed > 0) {
    return 'Есть задачи со сбоем или просрочкой. Приоритет — открыть проблемную запись и проверить причину исполнения.'
  }
  if (taskSummary.value.active > 0) {
    return 'Планировщик ведёт активные задачи без видимого разрыва в очереди. Можно наблюдать прогресс прямо в таймлайне.'
  }
  if (taskSummary.value.done > 0) {
    return 'Последние циклы завершались штатно. Экран готов к следующему запуску или ручной проверке деталей.'
  }
  return 'Очередь ещё не прогрета данными. Выполните синхронизацию, чтобы подтянуть последние задачи зоны.'
})

const weeklyTaskLoad = computed(() => {
  const counts = [0, 0, 0, 0, 0, 0, 0]
  for (const task of recentSchedulerTasks.value) {
    const timestamp = task.updated_at ?? task.created_at
    if (!timestamp) continue
    const date = new Date(timestamp)
    if (Number.isNaN(date.getTime())) continue
    const index = (date.getDay() + 6) % 7
    counts[index] += 1
  }

  const maxCount = Math.max(...counts, 1)
  const todayIndex = (new Date().getDay() + 6) % 7

  return WEEKDAY_LABELS.map((label, index) => ({
    label,
    count: counts[index],
    height: Math.max(12, Math.round((counts[index] / maxCount) * 100)),
    isToday: index === todayIndex,
  }))
})

const timelineEntries = computed<TimelineEntry[]>(() => {
  if (schedulerTaskTimeline.value.length > 0) {
    return schedulerTaskTimeline.value.slice(0, 6).map((step, index) => buildTimelineEntryFromEvent(step, index))
  }

  return filteredRecentSchedulerTasks.value.slice(0, 6).map((task) => buildTimelineEntryFromTask(task))
})

const executionSteps = computed<ExecutionStep[]>(() => {
  if (schedulerTaskTimeline.value.length > 0) {
    return schedulerTaskTimeline.value.slice(0, 8).map((step, index) => {
      const tone = resolveEventTone(step)
      return {
        id: step.event_id || `execution-${index}`,
        index: index + 1,
        tone,
        title: schedulerTaskTimelineStepLabel(step),
        subtitle: schedulerTaskTimelineStageLabel(step)
          || (step.reason_code ? schedulerTaskReasonLabel(step.reason_code, step.reason) : schedulerTaskEventLabel(step.event_type)),
        timeLabel: formatShortDateTime(step.at),
        badgeText: schedulerTaskEventLabel(step.event_type),
        badgeVariant: toneToBadgeVariant(tone),
      }
    })
  }

  if (schedulerTaskStatus.value?.process_steps?.length) {
    return schedulerTaskStatus.value.process_steps.slice(0, 8).map((step, index) => {
      const tone = resolveTaskTone(step.status)
      return {
        id: `${schedulerTaskStatus.value?.task_id}-process-${step.phase}-${index}`,
        index: index + 1,
        tone,
        title: step.label,
        subtitle: schedulerTaskProcessStatusLabel(step.status, step.status_label || null),
        timeLabel: formatShortDateTime(step.updated_at || step.started_at || null),
        badgeText: schedulerTaskProcessStatusLabel(step.status, step.status_label || null),
        badgeVariant: toneToBadgeVariant(tone),
      }
    })
  }

  if (latestRecentTask.value) {
    return [buildExecutionStepFromTask(latestRecentTask.value, 0)]
  }

  return []
})

const futureSchedulerTasks = computed(() => {
  return filteredRecentSchedulerTasks.value
    .filter((task) => task.task_id !== latestRecentTaskId.value)
    .filter((task) => {
      const bucket = classifySchedulerTaskStatus(task.status)
      return bucket === 'waiting' || bucket === 'active'
    })
    .slice(0, 6)
})

const timelineTaskGroups = computed<TimelineTaskGroup[]>(() => {
  const currentTasks = filteredRecentSchedulerTasks.value
    .filter((task) => task.task_id === latestRecentTaskId.value)
    .slice(0, 1)

  const futureTasks = futureSchedulerTasks.value
  const recentTasks = filteredRecentSchedulerTasks.value
    .filter((task) => task.task_id !== latestRecentTaskId.value)
    .filter((task) => !futureTasks.some((futureTask) => futureTask.task_id === task.task_id))
    .slice(0, 8)

  return [
    { key: 'current', label: 'Сейчас', tasks: currentTasks },
    { key: 'future', label: 'Дальше', tasks: futureTasks },
    { key: 'recent', label: 'Недавно', tasks: recentTasks },
  ].filter((group) => group.tasks.length > 0)
})

function onSchedulerTaskIdInputUpdate(value: string): void {
  schedulerTaskIdInput.value = value
}

function onSchedulerTaskSearchUpdate(value: string): void {
  schedulerTaskSearch.value = value
}

function onSchedulerTaskSearchInput(event: Event): void {
  const target = event.target as HTMLInputElement | null
  if (!target) return
  onSchedulerTaskSearchUpdate(target.value)
}

function onSchedulerTaskPresetUpdate(value: 'all' | 'failed' | 'deadline' | 'done_confirmed' | 'done_unconfirmed'): void {
  schedulerTaskPreset.value = value
}

function onSchedulerTaskPresetChange(event: Event): void {
  const target = event.target as HTMLSelectElement | null
  if (!target) return
  onSchedulerTaskPresetUpdate(target.value as 'all' | 'failed' | 'deadline' | 'done_confirmed' | 'done_unconfirmed')
}

function resetTaskFilters(): void {
  schedulerTaskSearch.value = ''
  schedulerTaskPreset.value = 'all'
}

function openLatestRecentTask(): void {
  if (!latestRecentTaskId.value) return
  void lookupSchedulerTask(latestRecentTaskId.value)
}

async function refreshSchedulerState(): Promise<void> {
  await fetchRecentSchedulerTasks()
  await fetchAutomationControlMode()
  if (!schedulerTaskStatus.value && latestRecentTaskId.value) {
    await lookupSchedulerTask(latestRecentTaskId.value)
  }
}

function isActiveSchedulerTask(status: string | null | undefined): boolean {
  const normalized = String(status ?? '').trim().toLowerCase()
  return normalized === 'accepted' || normalized === 'running' || normalized === 'queued' || normalized === 'scheduled'
}

function classifySchedulerTaskStatus(status: string | null | undefined): 'active' | 'waiting' | 'done' | 'failed' {
  const normalized = String(status ?? '').trim().toLowerCase()
  if (normalized === 'accepted' || normalized === 'running' || normalized === 'queued' || normalized === 'scheduled') {
    return 'active'
  }
  if (normalized === 'done' || normalized === 'completed' || normalized === 'confirmed' || normalized === 'succeeded') {
    return 'done'
  }
  if (normalized === 'failed' || normalized === 'error' || normalized === 'rejected' || normalized === 'canceled' || normalized === 'timeout' || normalized === 'expired') {
    return 'failed'
  }
  return 'waiting'
}

function formatManualStepLabel(step: AutomationManualStep): string {
  const labels: Record<AutomationManualStep, string> = {
    clean_fill_start: 'Чистый бак: старт',
    clean_fill_stop: 'Чистый бак: стоп',
    solution_fill_start: 'Раствор: старт',
    solution_fill_stop: 'Раствор: стоп',
    prepare_recirculation_start: 'Рециркуляция setup: старт',
    prepare_recirculation_stop: 'Рециркуляция setup: стоп',
    irrigation_recovery_start: 'Восстановление полива: старт',
    irrigation_recovery_stop: 'Восстановление полива: стоп',
  }

  return labels[step]
}

function presetIcon(value: 'all' | 'failed' | 'deadline' | 'done_confirmed' | 'done_unconfirmed'): string {
  if (value === 'failed') return 'error'
  if (value === 'deadline') return 'schedule'
  if (value === 'done_confirmed') return 'task_alt'
  if (value === 'done_unconfirmed') return 'radio_button_unchecked'
  return 'dataset'
}

function presetDescription(value: 'all' | 'failed' | 'deadline' | 'done_confirmed' | 'done_unconfirmed'): string {
  if (value === 'failed') return 'Показывает только ошибки и сбои, чтобы быстро найти проблемную цепочку.'
  if (value === 'deadline') return 'Выводит задачи, у которых сроки исполнения уже близки к SLA или просрочены.'
  if (value === 'done_confirmed') return 'Показывает завершённые задачи, у которых терминальный DONE подтверждён нодой.'
  if (value === 'done_unconfirmed') return 'Подсвечивает DONE без подтверждения эффекта на стороне ESP32.'
  return 'Полная очередь scheduler-задач с поиском по идентификатору, статусу и причине.'
}

function formatTelemetryMetric(value: number | null | undefined, digits = 1, suffix = ''): string | null {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  return `${value.toFixed(digits)}${suffix}`
}

function buildTimelineEntryFromTask(task: SchedulerTaskStatus): TimelineEntry {
  const tone = resolveTaskTone(task.status)
  const kindLabel = schedulerTaskTypeLabel(task.task_type)
  const reason = task.reason_code
    ? schedulerTaskReasonLabel(task.reason_code, task.reason || null)
    : 'Последняя запись очереди без дополнительной причины.'

  return {
    id: `task-${task.task_id}`,
    taskId: task.task_id,
    tone,
    icon: resolveTimelineIcon(task.task_type, task.status),
    timeLabel: formatShortDateTime(task.updated_at ?? task.created_at),
    statusLabel: schedulerTaskStatusLabel(task.status),
    kindLabel,
    title: `${kindLabel} · задача #${task.task_id}`,
    subtitle: reason,
    badgeText: schedulerTaskStatusLabel(task.status),
    badgeVariant: schedulerTaskStatusVariant(task.status),
    progress: timelineProgressByTone(tone),
  }
}

function buildExecutionStepFromTask(task: SchedulerTaskStatus, index: number): ExecutionStep {
  const tone = resolveTaskTone(task.status)
  return {
    id: `task-step-${task.task_id}`,
    index: index + 1,
    tone,
    title: `${schedulerTaskTypeLabel(task.task_type)} · #${task.task_id}`,
    subtitle: task.reason_code
      ? schedulerTaskReasonLabel(task.reason_code, task.reason || null)
      : schedulerTaskStatusLabel(task.status),
    timeLabel: formatShortDateTime(task.updated_at ?? task.created_at),
    badgeText: schedulerTaskStatusLabel(task.status),
    badgeVariant: schedulerTaskStatusVariant(task.status),
  }
}

function compactTaskSubtitle(task: SchedulerTaskStatus): string {
  if (task.reason_code) {
    return schedulerTaskReasonLabel(task.reason_code, task.reason || null)
  }

  return `${schedulerTaskTypeLabel(task.task_type)} · ${schedulerTaskStatusLabel(task.status)}`
}

function compactTaskMeta(task: SchedulerTaskStatus): string {
  const bucket = classifySchedulerTaskStatus(task.status)
  if (bucket === 'active') return 'В работе'
  if (bucket === 'waiting') return 'В очереди'
  if (bucket === 'done') return 'Завершена'
  return 'Проблема'
}

function buildTimelineEntryFromEvent(step: SchedulerTaskTimelineItem, index: number): TimelineEntry {
  const tone = resolveEventTone(step)
  const kindLabel = schedulerTaskTimelineStageLabel(step) || schedulerTaskEventLabel(step.event_type)
  const reason = step.error_code
    ? schedulerTaskErrorLabel(step.error_code)
    : step.reason_code
      ? schedulerTaskReasonLabel(step.reason_code, step.reason)
      : 'Событие lifecycle без дополнительного описания.'

  return {
    id: step.event_id || `timeline-${index}`,
    taskId: step.task_id ?? schedulerTaskStatus.value?.task_id ?? latestRecentTaskId.value ?? null,
    tone,
    icon: resolveTimelineIcon(step.task_type || step.event_type, step.status || step.terminal_status),
    timeLabel: formatShortDateTime(step.at),
    statusLabel: toneLabel(tone),
    kindLabel,
    title: schedulerTaskTimelineStepLabel(step),
    subtitle: reason,
    badgeText: schedulerTaskEventLabel(step.event_type),
    badgeVariant: toneToBadgeVariant(tone),
    progress: timelineProgressByTone(tone),
  }
}

function formatShortDateTime(value: string | null | undefined): string {
  if (!value) return 'Время не указано'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Время не указано'

  return new Intl.DateTimeFormat('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
  }).format(date)
}

function resolveTaskTone(status: string | null | undefined): TimelineTone {
  const bucket = classifySchedulerTaskStatus(status)
  if (bucket === 'active') return 'running'
  if (bucket === 'done') return 'done'
  if (bucket === 'failed') return 'failed'
  return 'waiting'
}

function resolveEventTone(step: SchedulerTaskTimelineItem): TimelineTone {
  const normalizedStatus = String(step.status ?? step.terminal_status ?? '').trim().toLowerCase()
  const normalizedEvent = String(step.event_type ?? '').trim().toLowerCase()

  if (normalizedStatus === 'failed' || normalizedStatus === 'error' || normalizedStatus === 'expired' || step.error_code) {
    return 'failed'
  }
  if (normalizedStatus === 'completed' || normalizedStatus === 'done' || normalizedStatus === 'succeeded') {
    return 'done'
  }
  if (normalizedStatus === 'running' || normalizedEvent.includes('start') || normalizedEvent.includes('running')) {
    return 'running'
  }
  return 'waiting'
}

function resolveTimelineIcon(kind: string | null | undefined, status: string | null | undefined): string {
  const normalized = String(kind ?? '').trim().toLowerCase()
  const normalizedStatus = String(status ?? '').trim().toLowerCase()

  if (normalizedStatus === 'failed' || normalizedStatus === 'error' || normalized.includes('error')) return 'error'
  if (normalized.includes('irrig') || normalized.includes('water') || normalized.includes('fill')) return 'water_drop'
  if (normalized.includes('light')) return 'light_mode'
  if (normalized.includes('vent') || normalized.includes('air') || normalized.includes('climate')) return 'air'
  if (normalized.includes('diag') || normalized.includes('setup') || normalized.includes('prepare')) return 'tune'
  return 'schedule'
}

function toneLabel(tone: TimelineTone): string {
  if (tone === 'running') return 'Выполняется'
  if (tone === 'done') return 'Завершено'
  if (tone === 'failed') return 'Ошибка'
  return 'Ожидание'
}

function toneToBadgeVariant(tone: TimelineTone): 'success' | 'warning' | 'danger' | 'info' | 'secondary' {
  if (tone === 'running') return 'warning'
  if (tone === 'done') return 'success'
  if (tone === 'failed') return 'danger'
  return 'secondary'
}

function timelineProgressByTone(tone: TimelineTone): number {
  if (tone === 'running') return 68
  if (tone === 'done') return 100
  if (tone === 'failed') return 100
  return 28
}

function timelineDotClass(tone: TimelineTone): string {
  if (tone === 'running') return 'bg-emerald-600'
  if (tone === 'done') return 'bg-cyan-600'
  if (tone === 'failed') return 'bg-rose-600'
  return 'bg-slate-500'
}

function timelineCardClass(tone: TimelineTone): string {
  if (tone === 'running') return 'border-emerald-200 bg-emerald-50/60'
  if (tone === 'done') return 'border-cyan-200 bg-cyan-50/50'
  if (tone === 'failed') return 'border-rose-200 bg-rose-50/60'
  return 'border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/45'
}

function timelinePillClass(tone: TimelineTone): string {
  if (tone === 'running') return 'bg-emerald-100 text-emerald-900'
  if (tone === 'done') return 'bg-cyan-100 text-cyan-900'
  if (tone === 'failed') return 'bg-rose-100 text-rose-900'
  return 'bg-[color:var(--surface-card)] text-[color:var(--text-dim)]'
}

function timelineBarClass(tone: TimelineTone): string {
  if (tone === 'running') return 'bg-emerald-500'
  if (tone === 'done') return 'bg-cyan-500'
  if (tone === 'failed') return 'bg-rose-500'
  return 'bg-slate-400'
}

const WEEKDAY_LABELS = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']

onMounted(() => {
  void refreshSchedulerState()
  if (import.meta.env.MODE !== 'test') {
    void scheduler.pollSchedulerTasksCycle()
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange)
    }
  }
})

onUnmounted(() => {
  clearSchedulerTasksPollTimer()
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
})

watch(
  () => props.zoneId,
  () => {
    resetForZoneChange()
    void refreshSchedulerState()
    scheduleSchedulerTasksPoll()
  }
)
</script>
