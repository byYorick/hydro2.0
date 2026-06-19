<template>
  <section
    class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/55 p-4"
    data-testid="manual-schedules-section"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold text-[color:var(--text-primary)]">
          Ручные расписания
        </h3>
        <p class="mt-0.5 max-w-2xl text-xs text-[color:var(--text-dim)]">
          Дополняют рецепт и участвуют в dispatch планировщика. Время — UTC.
        </p>
      </div>
      <Button
        v-if="canManage"
        size="sm"
        variant="secondary"
        data-testid="manual-schedule-create"
        @click="openCreate"
      >
        + Добавить расписание
      </Button>
    </div>

    <div
      v-if="loading"
      class="mt-4 rounded-xl border border-[color:var(--border-muted)] px-4 py-8 text-center"
      data-testid="manual-schedules-loading"
    >
      <p class="text-sm text-[color:var(--text-muted)]">
        Загрузка расписаний…
      </p>
    </div>

    <div
      v-else-if="schedules.length === 0"
      class="mt-4 rounded-xl border border-dashed border-[color:var(--border-muted)] px-4 py-8 text-center"
    >
      <p class="text-sm text-[color:var(--text-muted)]">
        Нет ручных правил
      </p>
      <p class="mt-1 text-xs text-[color:var(--text-dim)]">
        {{ canManage ? 'Создайте полив, свет, климат или разовое задание.' : 'Доступно агроному или администратору.' }}
      </p>
    </div>

    <div
      v-else
      class="mt-4 overflow-x-auto"
    >
      <table
        class="w-full min-w-[640px] text-left text-[11px]"
        aria-label="Ручные расписания зоны"
      >
        <thead>
          <tr class="border-b border-[color:var(--border-muted)] text-[color:var(--text-dim)]">
            <th class="px-2 py-2 font-medium">
              Статус
            </th>
            <th class="px-2 py-2 font-medium">
              Задача
            </th>
            <th class="px-2 py-2 font-medium">
              Расписание
            </th>
            <th class="px-2 py-2 font-medium">
              Ближайший запуск
            </th>
            <th
              v-if="canManage"
              class="px-2 py-2 font-medium text-right"
            >
              Действия
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="schedule in schedules"
            :key="schedule.id"
            class="border-b border-[color:var(--border-muted)]/60"
            data-testid="manual-schedule-row"
          >
            <td class="px-2 py-2.5">
              <div class="flex flex-col gap-1">
                <button
                  v-if="canManage"
                  type="button"
                  role="switch"
                  :aria-checked="schedule.enabled"
                  :aria-label="schedule.label ? `Активно: ${schedule.label}` : `Активно: ${laneLabel(schedule.task_type)}`"
                  class="relative inline-flex h-5 w-9 shrink-0 rounded-full transition motion-reduce:transition-none"
                  :class="schedule.enabled ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--border-muted)]'"
                  :disabled="togglingId === schedule.id"
                  @click="toggleEnabled(schedule)"
                >
                  <span
                    class="absolute top-0.5 h-4 w-4 rounded-full bg-white transition motion-reduce:transition-none"
                    :class="schedule.enabled ? 'left-[18px]' : 'left-0.5'"
                  />
                </button>
                <Badge
                  v-else
                  :variant="schedule.enabled ? 'success' : 'secondary'"
                  size="xs"
                >
                  {{ schedule.enabled ? 'активно' : 'выкл' }}
                </Badge>
                <Badge
                  v-if="isOnceCompleted(schedule)"
                  variant="secondary"
                  size="xs"
                >
                  выполнено
                </Badge>
              </div>
            </td>
            <td class="px-2 py-2.5">
              <div class="flex flex-wrap items-center gap-1.5">
                <Badge
                  size="xs"
                  :variant="taskBadgeVariant(schedule.task_type)"
                >
                  {{ laneLabel(schedule.task_type) }}
                </Badge>
                <span
                  v-if="!isExecutable(schedule.task_type)"
                  class="text-[10px] text-amber-400/90"
                  title="Без автозапуска на AE3"
                >
                  план
                </span>
              </div>
              <div
                v-if="schedule.label"
                class="mt-0.5 text-[color:var(--text-primary)]"
              >
                {{ schedule.label }}
              </div>
            </td>
            <td class="px-2 py-2.5 text-[color:var(--text-muted)]">
              {{ schedule.summary || buildManualScheduleSummary(toManualSchedulePayload(schedule)) }}
            </td>
            <td class="px-2 py-2.5 text-[color:var(--text-primary)]">
              {{ nextTriggerLabel(schedule) }}
            </td>
            <td
              v-if="canManage"
              class="px-2 py-2.5"
            >
              <div class="flex justify-end gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  class="h-7 px-2 text-[10px]"
                  @click="openEdit(schedule)"
                >
                  Изм.
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  class="h-7 px-2 text-[10px]"
                  @click="duplicateSchedule(schedule)"
                >
                  Копия
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  class="h-7 px-2 text-[10px] text-red-500"
                  @click="removeSchedule(schedule)"
                >
                  Удал.
                </Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ManualScheduleFormModal
      :open="modalOpen"
      :initial="modalInitial"
      :saving="saving"
      :executable-task-types="executableTaskTypes"
      :server-errors="serverErrors"
      @close="closeModal"
      @clear-server-errors="serverErrors = {}"
      @submit="handleSubmit"
    />

    <Modal
      :open="deleteTarget !== null"
      title="Удалить расписание?"
      hide-default-cancel
      @close="deleteTarget = null"
    >
      <p class="text-sm text-[color:var(--text-muted)]">
        {{ deleteTarget?.label || buildManualScheduleSummary(toManualSchedulePayload(deleteTarget!)) }}
      </p>
      <template #footer>
        <Button
          size="sm"
          variant="ghost"
          @click="deleteTarget = null"
        >
          Отмена
        </Button>
        <Button
          size="sm"
          variant="danger"
          :disabled="deleting"
          @click="confirmDelete"
        >
          {{ deleting ? 'Удаляем...' : 'Удалить' }}
        </Button>
      </template>
    </Modal>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import ManualScheduleFormModal from '@/Components/Scheduler/ManualScheduleFormModal.vue'
import type {
  PlanWindow,
  ZoneManualSchedule,
  ZoneManualSchedulePayload,
} from '@/composables/zoneScheduleWorkspaceTypes'
import { api } from '@/services/api'
import {
  buildManualScheduleSummary,
  formatRelativeUtc,
  isTaskExecutableOnAe3,
  toManualSchedulePayload,
} from '@/utils/manualSchedulePreview'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  zoneId: number | null | undefined
  schedules: ZoneManualSchedule[]
  loading?: boolean
  canManage: boolean
  laneLabel: (taskType: string) => string
  executableTaskTypes: string[]
  planWindows: PlanWindow[]
}>()

const emit = defineEmits<{
  changed: []
}>()

const { showToast } = useToast()

const modalOpen = ref(false)
const saving = ref(false)
const deleting = ref(false)
const togglingId = ref<number | null>(null)
const editingSchedule = ref<ZoneManualSchedule | null>(null)
const duplicateDraft = ref<ZoneManualSchedule | null>(null)
const deleteTarget = ref<ZoneManualSchedule | null>(null)
const serverErrors = ref<Record<string, string[]>>({})

const modalInitial = computed(() => editingSchedule.value ?? duplicateDraft.value)

function isOnceCompleted(schedule: ZoneManualSchedule): boolean {
  return schedule.schedule_kind === 'once' && Boolean(schedule.last_dispatched_at)
}

function requireZoneId(): number | null {
  if (!props.zoneId) {
    showToast('Зона не выбрана.', 'error')
    return null
  }
  return props.zoneId
}

function isExecutable(taskType: string): boolean {
  return isTaskExecutableOnAe3(taskType, props.executableTaskTypes)
}

function taskBadgeVariant(taskType: string): 'success' | 'warning' | 'info' | 'secondary' {
  if (taskType === 'irrigation') return 'info'
  if (taskType === 'lighting') return 'warning'
  if (taskType === 'diagnostics') return 'secondary'
  return 'secondary'
}

function nextTriggerLabel(schedule: ZoneManualSchedule): string {
  if (isOnceCompleted(schedule)) return 'выполнено'
  if (!schedule.enabled) return 'выкл'

  const fromPlan = props.planWindows.find((w) => w.manual_schedule_id === schedule.id)
  if (fromPlan?.trigger_at) {
    return formatRelativeUtc(fromPlan.trigger_at)
  }

  return '—'
}

function openCreate(): void {
  const zoneId = requireZoneId()
  if (!zoneId) return
  editingSchedule.value = null
  duplicateDraft.value = null
  serverErrors.value = {}
  modalOpen.value = true
}

function openEdit(schedule: ZoneManualSchedule): void {
  editingSchedule.value = schedule
  duplicateDraft.value = null
  serverErrors.value = {}
  modalOpen.value = true
}

function closeModal(): void {
  modalOpen.value = false
  editingSchedule.value = null
  duplicateDraft.value = null
  serverErrors.value = {}
}

function extractValidationErrors(error: unknown): Record<string, string[]> {
  const candidate = error as { response?: { data?: { errors?: Record<string, string[]> } } }
  return candidate.response?.data?.errors ?? {}
}

async function handleSubmit(payload: ZoneManualSchedulePayload): Promise<void> {
  const zoneId = requireZoneId()
  if (!zoneId) return

  saving.value = true
  serverErrors.value = {}
  try {
    if (editingSchedule.value?.id) {
      await api.zones.updateManualSchedule(zoneId, editingSchedule.value.id, payload)
      showToast('Расписание обновлено.', 'success')
    } else {
      await api.zones.createManualSchedule(zoneId, payload)
      showToast('Расписание создано.', 'success')
    }
    closeModal()
    emit('changed')
  } catch (error) {
    const errors = extractValidationErrors(error)
    if (Object.keys(errors).length > 0) {
      serverErrors.value = errors
    } else {
      showToast('Не удалось сохранить расписание.', 'error')
    }
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(schedule: ZoneManualSchedule): Promise<void> {
  const zoneId = requireZoneId()
  if (!zoneId || !schedule.id) return

  if (isOnceCompleted(schedule) && !schedule.enabled) {
    showToast('Для повторного включения укажите новый run_at в будущем (UTC).', 'error')
    openEdit(schedule)
    return
  }

  togglingId.value = schedule.id
  try {
    await api.zones.updateManualSchedule(zoneId, schedule.id, { enabled: !schedule.enabled })
    emit('changed')
  } catch (error) {
    const errors = extractValidationErrors(error)
    showToast(errors.enabled?.[0] ?? 'Не удалось изменить статус.', 'error')
  } finally {
    togglingId.value = null
  }
}

function duplicateSchedule(schedule: ZoneManualSchedule): void {
  if (!requireZoneId()) return

  const draft: ZoneManualSchedule = {
    ...schedule,
    id: undefined as unknown as number,
    label: schedule.label ? `${schedule.label} (копия)` : undefined,
    last_dispatched_at: undefined,
    enabled: true,
  }

  if (schedule.schedule_kind === 'once') {
    draft.run_at = new Date(Date.now() + 24 * 3_600_000).toISOString()
  }

  editingSchedule.value = null
  duplicateDraft.value = draft
  serverErrors.value = {}
  modalOpen.value = true
}

function removeSchedule(schedule: ZoneManualSchedule): void {
  if (!requireZoneId() || !schedule.id) return
  deleteTarget.value = schedule
}

async function confirmDelete(): Promise<void> {
  const zoneId = requireZoneId()
  if (!zoneId || !deleteTarget.value?.id) return

  deleting.value = true
  try {
    await api.zones.deleteManualSchedule(zoneId, deleteTarget.value.id)
    showToast('Расписание удалено.', 'success')
    deleteTarget.value = null
    emit('changed')
  } catch {
    showToast('Не удалось удалить расписание.', 'error')
  } finally {
    deleting.value = false
  }
}
</script>
