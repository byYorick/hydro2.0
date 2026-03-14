<template>
  <details class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl group">
    <summary class="cursor-pointer px-4 py-3 list-none flex items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <span class="text-sm font-medium text-[color:var(--text-primary)]">Задачи автоматики</span>
        <Badge variant="secondary">диагностика</Badge>
      </div>
      <span class="text-xs text-[color:var(--text-dim)]">открыть панель</span>
    </summary>

    <div class="p-4 space-y-4 border-t border-[color:var(--border-muted)]">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <p class="text-xs text-[color:var(--text-dim)]">
          Здесь можно понять, что делает автоматика сейчас, почему задача зависла или завершилась ошибкой, и на каком этапе это произошло.
        </p>
        <div class="text-xs text-[color:var(--text-muted)]">
          <span v-if="schedulerTasksUpdatedAt">Обновлено: {{ formatDateTime(schedulerTasksUpdatedAt) }}</span>
          <span v-else>Ожидание данных</span>
        </div>
      </div>

      <div class="flex flex-col md:flex-row gap-2">
        <input
          v-model="taskIdModel"
          type="text"
          class="w-full md:flex-1 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)] px-3 py-2 text-sm"
          placeholder="Введите numeric ID задачи: 78"
        />
        <div class="flex gap-2">
          <Button
            size="sm"
            :disabled="schedulerTaskLookupLoading"
            @click="$emit('lookup-task')"
          >
            {{ schedulerTaskLookupLoading ? 'Открываем...' : 'Открыть задачу' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="schedulerTaskListLoading"
            @click="$emit('refresh-list')"
          >
            {{ schedulerTaskListLoading ? 'Обновляем...' : 'Обновить список задач' }}
          </Button>
        </div>
      </div>

      <p
        v-if="schedulerTaskError"
        class="text-xs text-red-500"
      >
        {{ schedulerTaskError }}
      </p>

      <p
        v-if="!schedulerTaskStatus"
        class="text-xs text-[color:var(--text-dim)]"
      >
        Выберите задачу из списка ниже или введите её ID вручную.
      </p>

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

      <div class="space-y-2">
        <h4 class="text-sm font-medium text-[color:var(--text-primary)]">Последние задачи зоны</h4>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-2">
          <input
            v-model="taskSearchModel"
            type="text"
            class="w-full rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)] px-3 py-2 text-xs"
            placeholder="Поиск: ID, статус, причина, ошибка"
          />
          <select
            v-model="taskPresetModel"
            class="w-full rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)] px-3 py-2 text-xs"
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
            @click="resetFilters"
          >
            Сбросить фильтры
          </Button>
        </div>

        <ul
          v-if="filteredRecentSchedulerTasks.length > 0"
          class="space-y-2"
        >
          <li
            v-for="task in filteredRecentSchedulerTasks"
            :key="task.task_id"
            class="flex flex-col md:flex-row md:items-center md:justify-between gap-2 rounded-xl border border-[color:var(--border-muted)] px-3 py-2"
          >
            <div class="min-w-0">
              <p class="font-mono text-xs text-[color:var(--text-primary)] truncate">{{ task.task_id }}</p>
              <p class="text-xs text-[color:var(--text-dim)]">
                {{ schedulerTaskTypeLabel(task.task_type) }} · {{ formatDateTime(task.updated_at) }}
              </p>
              <p
                v-if="task.reason_code"
                class="text-[11px] text-[color:var(--text-muted)] truncate"
              >
                Причина: {{ schedulerTaskReasonLabel(task.reason_code, task.reason || null) }}
              </p>
            </div>
            <div class="flex items-center gap-2">
              <Badge :variant="schedulerTaskStatusVariant(task.status)">
                {{ schedulerTaskStatusLabel(task.status) }}
              </Badge>
              <Button
                size="sm"
                variant="outline"
                @click="$emit('lookup-task', task.task_id)"
              >
                Открыть
              </Button>
            </div>
          </li>
        </ul>
        <p
          v-else
          class="text-xs text-[color:var(--text-dim)]"
        >
          По текущим фильтрам задачи не найдены.
        </p>
      </div>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import ZoneAutomationSchedulerTaskDetailsCard from '@/Pages/Zones/Tabs/ZoneAutomationSchedulerTaskDetailsCard.vue'
import type {
  SchedulerTaskDoneMeta,
  SchedulerTaskPreset,
  SchedulerTaskSlaMeta,
  SchedulerTaskStatus,
  SchedulerTaskTimelineItem,
} from '@/composables/zoneAutomationTypes'

interface Props {
  schedulerTaskIdInput: string
  schedulerTaskLookupLoading: boolean
  schedulerTaskListLoading: boolean
  schedulerTaskError: string | null
  schedulerTaskStatus: SchedulerTaskStatus | null
  schedulerTaskSla: SchedulerTaskSlaMeta
  schedulerTaskDone: SchedulerTaskDoneMeta
  schedulerTaskTimeline: SchedulerTaskTimelineItem[]
  formatDateTime: (value: string | null | undefined) => string
  schedulerTaskStatusVariant: (value: string | null | undefined) => 'success' | 'warning' | 'danger' | 'info' | 'secondary'
  schedulerTaskStatusLabel: (value: string | null | undefined) => string
  schedulerTaskTypeLabel: (value: string | null | undefined) => string
  schedulerTaskDecisionLabel: (value: string | null | undefined) => string
  schedulerTaskReasonLabel: (reasonCode: string | null | undefined, reasonText?: string | null | undefined) => string
  schedulerTaskErrorLabel: (value: string | null | undefined, rawError?: string | null | undefined) => string
  schedulerTaskProcessStatusVariant: (value: string | null | undefined) => 'success' | 'warning' | 'danger' | 'info' | 'secondary'
  schedulerTaskProcessStatusLabel: (value: string | null | undefined, statusLabel?: string | null | undefined) => string
  schedulerTaskEventLabel: (value: string | null | undefined) => string
  schedulerTaskTimelineStepLabel: (value: SchedulerTaskTimelineItem) => string
  schedulerTaskTimelineStageLabel: (value: SchedulerTaskTimelineItem) => string | null
  filteredRecentSchedulerTasks: SchedulerTaskStatus[]
  schedulerTaskSearch: string
  schedulerTaskPreset: SchedulerTaskPreset
  schedulerTaskPresetOptions: Array<{ value: SchedulerTaskPreset; label: string }>
  schedulerTasksUpdatedAt: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'lookup-task', taskId?: string): void
  (e: 'refresh-list'): void
  (e: 'update:schedulerTaskIdInput', value: string): void
  (e: 'update:schedulerTaskSearch', value: string): void
  (e: 'update:schedulerTaskPreset', value: SchedulerTaskPreset): void
}>()

const taskIdModel = computed({
  get: () => props.schedulerTaskIdInput,
  set: (value: string) => emit('update:schedulerTaskIdInput', value),
})

const taskSearchModel = computed({
  get: () => props.schedulerTaskSearch,
  set: (value: string) => emit('update:schedulerTaskSearch', value),
})

const taskPresetModel = computed({
  get: () => props.schedulerTaskPreset,
  set: (value: SchedulerTaskPreset) => emit('update:schedulerTaskPreset', value),
})

function resetFilters(): void {
  emit('update:schedulerTaskPreset', 'all')
  emit('update:schedulerTaskSearch', '')
}
</script>
