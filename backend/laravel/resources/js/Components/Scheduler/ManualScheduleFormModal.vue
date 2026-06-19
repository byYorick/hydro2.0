<template>
  <Modal
    :open="open"
    size="large"
    :title="isCreate ? 'Новое расписание' : 'Изменить расписание'"
    data-testid="manual-schedule-modal"
    @close="$emit('close')"
  >
    <div
      v-if="generalError"
      class="mb-3 rounded-xl border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-400"
    >
      {{ generalError }}
    </div>

    <div class="grid gap-5 md:grid-cols-[1.4fr_1fr]">
      <div class="space-y-4">
        <div>
          <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-[color:var(--text-muted)]">
            Тип задачи
          </div>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <button
              v-for="option in taskOptions"
              :key="option.value"
              type="button"
              class="rounded-xl border px-3 py-2.5 text-left transition motion-reduce:transition-none"
              :class="taskCardClass(option)"
              :aria-pressed="form.task_type === option.value"
              :data-testid="`manual-schedule-task-type-${option.value}`"
              @click="form.task_type = option.value"
            >
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                {{ option.label }}
              </div>
              <div class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">
                {{ option.hint }}
              </div>
            </button>
          </div>
          <p
            v-if="fieldError('task_type')"
            class="mt-1 text-xs text-red-400"
          >
            {{ fieldError('task_type') }}
          </p>
        </div>

        <div
          v-if="showNonExecutableWarning"
          class="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200/90"
        >
          На AE3 этот тип появится в плане, но без автоматического запуска.
        </div>

        <div>
          <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-[color:var(--text-muted)]">
            Вид расписания
          </div>
          <div
            class="inline-flex rounded-xl bg-[color:var(--bg-main)]/40 p-0.5"
            role="group"
            aria-label="Вид расписания"
          >
            <button
              v-for="option in kindOptions"
              :key="option.value"
              type="button"
              class="rounded-lg px-3 py-1.5 text-xs font-medium transition motion-reduce:transition-none"
              :class="form.schedule_kind === option.value
                ? 'bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)] shadow-sm'
                : 'text-[color:var(--text-dim)] hover:text-[color:var(--text-muted)]'"
              :aria-pressed="form.schedule_kind === option.value"
              :data-testid="`manual-schedule-kind-${option.value}`"
              @click="form.schedule_kind = option.value"
            >
              {{ option.label }}
            </button>
          </div>
        </div>

        <div
          v-if="form.schedule_kind !== 'once'"
          class="space-y-2"
        >
          <div class="text-xs font-semibold uppercase tracking-wide text-[color:var(--text-muted)]">
            Дни недели
          </div>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="day in weekdayOptions"
              :key="day.value"
              type="button"
              class="rounded-full border px-2.5 py-1 text-xs transition motion-reduce:transition-none"
              :class="selectedDays.includes(day.value)
                ? 'border-[color:var(--accent-cyan)] bg-[color-mix(in_srgb,var(--accent-cyan)_18%,transparent)] text-[color:var(--text-primary)]'
                : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent-cyan)_40%,transparent)]'"
              :data-testid="`manual-schedule-weekday-${day.value}`"
              @click="toggleDay(day.value)"
            >
              {{ day.label }}
            </button>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <Button
              size="sm"
              variant="ghost"
              class="h-7 px-2 text-[10px]"
              @click="setDayPreset('weekdays')"
            >
              Будни
            </Button>
            <Button
              size="sm"
              variant="ghost"
              class="h-7 px-2 text-[10px]"
              @click="setDayPreset('weekend')"
            >
              Выходные
            </Button>
            <Button
              size="sm"
              variant="ghost"
              class="h-7 px-2 text-[10px]"
              @click="setDayPreset('all')"
            >
              Каждый день
            </Button>
          </div>
        </div>

        <div v-if="form.schedule_kind === 'time'">
          <label class="mb-1 block text-xs text-[color:var(--text-muted)]">Время запуска (UTC)</label>
          <input
            v-model="form.time_at"
            type="time"
            class="input-field"
            data-testid="manual-schedule-time-at"
          >
          <p
            v-if="fieldError('time_at')"
            class="mt-1 text-xs text-red-400"
          >
            {{ fieldError('time_at') }}
          </p>
        </div>

        <div
          v-if="form.schedule_kind === 'interval'"
          class="grid grid-cols-[1fr_auto] gap-2"
        >
          <div>
            <label class="mb-1 block text-xs text-[color:var(--text-muted)]">Интервал</label>
            <input
              v-model.number="intervalValue"
              type="number"
              :min="intervalMinValue"
              :max="intervalMaxValue"
              class="input-field"
              data-testid="manual-schedule-interval"
            >
          </div>
          <div>
            <label class="mb-1 block text-xs text-[color:var(--text-muted)]">Единица</label>
            <select
              v-model="intervalUnit"
              class="input-field"
              data-testid="manual-schedule-interval-unit"
            >
              <option value="minutes">
                мин
              </option>
              <option value="hours">
                ч
              </option>
            </select>
          </div>
          <p class="col-span-2 text-[10px] text-[color:var(--text-dim)]">
            = {{ form.interval_sec ?? 0 }} с
          </p>
          <p
            v-if="fieldError('interval_sec')"
            class="col-span-2 text-xs text-red-400"
          >
            {{ fieldError('interval_sec') }}
          </p>
        </div>

        <div
          v-if="form.schedule_kind === 'window'"
          class="grid grid-cols-2 gap-2"
        >
          <div>
            <label class="mb-1 block text-xs text-[color:var(--text-muted)]">Начало (UTC)</label>
            <input
              v-model="form.window_start"
              type="time"
              class="input-field"
            >
          </div>
          <div>
            <label class="mb-1 block text-xs text-[color:var(--text-muted)]">Конец (UTC)</label>
            <input
              v-model="form.window_end"
              type="time"
              class="input-field"
            >
          </div>
          <p
            v-if="fieldError('window_start') || fieldError('window_end')"
            class="col-span-2 text-xs text-red-400"
          >
            {{ fieldError('window_start') || fieldError('window_end') }}
          </p>
        </div>

        <div v-if="form.schedule_kind === 'once'">
          <label class="mb-1 block text-xs text-[color:var(--text-muted)]">Дата и время (UTC)</label>
          <input
            v-model="runAtLocal"
            type="datetime-local"
            class="input-field"
            data-testid="manual-schedule-run-at"
          >
          <p class="mt-1 text-[10px] text-[color:var(--text-dim)]">
            Сработает один раз в указанный момент. Время вводится в UTC, не в локальном часовом поясе браузера.
          </p>
          <p
            v-if="fieldError('run_at')"
            class="mt-1 text-xs text-red-400"
          >
            {{ fieldError('run_at') }}
          </p>
        </div>

        <div v-if="form.task_type === 'irrigation'">
          <label class="mb-1 block text-xs text-[color:var(--text-muted)]">Длительность полива</label>
          <div class="grid grid-cols-[1fr_auto] gap-2">
            <input
              v-model.number="durationValue"
              type="number"
              :min="durationMinValue"
              :max="durationMaxValue"
              class="input-field"
              data-testid="manual-schedule-duration"
            >
            <select
              v-model="durationUnit"
              class="input-field"
            >
              <option value="seconds">
                сек
              </option>
              <option value="minutes">
                мин
              </option>
            </select>
          </div>
          <p
            v-if="fieldError('payload.duration_sec')"
            class="mt-1 text-xs text-red-400"
          >
            {{ fieldError('payload.duration_sec') }}
          </p>
        </div>

        <div>
          <label class="mb-1 block text-xs text-[color:var(--text-muted)]">Подпись (необязательно)</label>
          <input
            v-model="form.label"
            type="text"
            maxlength="255"
            class="input-field"
            placeholder="Например: вечерний полив"
          >
        </div>

        <label class="flex items-center gap-2 text-xs text-[color:var(--text-muted)]">
          <button
            type="button"
            role="switch"
            :aria-checked="form.enabled"
            class="relative h-5 w-9 rounded-full transition motion-reduce:transition-none"
            :class="form.enabled ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--border-muted)]'"
            data-testid="manual-schedule-enabled-toggle"
            @click="form.enabled = !form.enabled"
          >
            <span
              class="absolute top-0.5 h-4 w-4 rounded-full bg-white transition motion-reduce:transition-none"
              :class="form.enabled ? 'left-[18px]' : 'left-0.5'"
            />
          </button>
          Активно
        </label>
        <p
          v-if="fieldError('enabled')"
          class="mt-1 text-xs text-red-400"
        >
          {{ fieldError('enabled') }}
        </p>
      </div>

      <aside
        class="sticky top-0 rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-main)]/30 p-3"
        data-testid="manual-schedule-preview"
      >
        <div class="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
          Предпросмотр
        </div>
        <p class="mt-2 text-sm font-medium leading-snug text-[color:var(--text-primary)]">
          {{ summaryText }}
        </p>
        <ul
          v-if="previewTriggers.length"
          class="mt-3 space-y-1.5"
        >
          <li
            v-for="(trigger, index) in previewTriggers"
            :key="trigger.at"
            class="flex items-center justify-between rounded-lg border border-[color:var(--border-muted)]/70 px-2 py-1.5 text-[11px]"
          >
            <span class="text-[color:var(--text-muted)]">#{{ index + 1 }}</span>
            <span class="font-medium text-[color:var(--text-primary)]">{{ trigger.relativeLabel }}</span>
          </li>
        </ul>
        <p
          v-else-if="form.schedule_kind === 'interval'"
          class="mt-3 text-[11px] text-[color:var(--text-dim)]"
        >
          Оценка. Точное время после сохранения — в колонке «Ближайший запуск».
        </p>
        <p
          v-else
          class="mt-3 text-[11px] text-[color:var(--text-dim)]"
        >
          Заполните параметры, чтобы увидеть ближайшие запуски.
        </p>
      </aside>
    </div>

    <p
      v-if="!isValid && validationHint"
      class="mt-3 text-xs text-amber-400/90"
      data-testid="manual-schedule-validation-hint"
    >
      {{ validationHint }}
    </p>

    <template #footer>
      <Button
        size="sm"
        :disabled="saving || !isValid"
        data-testid="manual-schedule-submit"
        @click="submit"
      >
        {{ saving ? 'Сохраняем...' : 'Сохранить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import type { ZoneManualSchedule, ZoneManualSchedulePayload } from '@/composables/zoneScheduleWorkspaceTypes'
import {
  MANUAL_SCHEDULE_KIND_OPTIONS,
  MANUAL_SCHEDULE_LIMITS,
  MANUAL_SCHEDULE_TASK_OPTIONS,
  WEEKDAY_OPTIONS,
  buildManualScheduleSummary,
  collectManualScheduleFormErrors,
  isManualScheduleFormValid,
  isTaskExecutableOnAe3,
  previewManualScheduleTriggers,
} from '@/utils/manualSchedulePreview'

const props = defineProps<{
  open: boolean
  initial: ZoneManualSchedule | null
  saving: boolean
  executableTaskTypes: string[]
  serverErrors?: Record<string, string[]>
}>()

const emit = defineEmits<{
  close: []
  submit: [ZoneManualSchedulePayload]
  clearServerErrors: []
}>()

const taskOptions = MANUAL_SCHEDULE_TASK_OPTIONS
const kindOptions = MANUAL_SCHEDULE_KIND_OPTIONS
const weekdayOptions = WEEKDAY_OPTIONS

const form = reactive<ZoneManualSchedulePayload>({
  task_type: 'irrigation',
  schedule_kind: 'time',
  time_at: '08:00',
  interval_sec: 3600,
  window_start: '06:00',
  window_end: '22:00',
  days_of_week: [],
  label: '',
  enabled: true,
  payload: { duration_sec: 60 },
})

const intervalUnit = ref<'minutes' | 'hours'>('hours')
const intervalValue = ref(1)
const durationUnit = ref<'seconds' | 'minutes'>('seconds')
const durationValue = ref(60)
const runAtLocal = ref('')
const localErrors = ref<Record<string, string[]>>({})

const selectedDays = computed(() => form.days_of_week ?? [])

const mergedErrors = computed(() => ({ ...localErrors.value, ...(props.serverErrors ?? {}) }))

const generalError = computed(() => mergedErrors.value.general?.[0] ?? null)

const isCreate = computed(() => !props.initial?.id)

const isValid = computed(() => isManualScheduleFormValid(form, { isCreate: isCreate.value }))

const validationHint = computed(() => {
  const errors = collectManualScheduleFormErrors(form, { isCreate: isCreate.value })
  const messages = Object.values(errors).flat()
  return messages[0] ?? null
})

const durationMinValue = computed(() => (
  durationUnit.value === 'minutes'
    ? Math.ceil(MANUAL_SCHEDULE_LIMITS.durationSec.min / 60)
    : MANUAL_SCHEDULE_LIMITS.durationSec.min
))

const durationMaxValue = computed(() => (
  durationUnit.value === 'minutes'
    ? Math.floor(MANUAL_SCHEDULE_LIMITS.durationSec.max / 60)
    : MANUAL_SCHEDULE_LIMITS.durationSec.max
))

const intervalMinValue = computed(() => (
  intervalUnit.value === 'hours'
    ? Math.ceil(MANUAL_SCHEDULE_LIMITS.intervalSec.min / 3600)
    : Math.ceil(MANUAL_SCHEDULE_LIMITS.intervalSec.min / 60)
))

const intervalMaxValue = computed(() => (
  intervalUnit.value === 'hours'
    ? Math.floor(MANUAL_SCHEDULE_LIMITS.intervalSec.max / 3600)
    : Math.floor(MANUAL_SCHEDULE_LIMITS.intervalSec.max / 60)
))

const summaryText = computed(() => buildManualScheduleSummary(form))

const previewTriggers = computed(() => previewManualScheduleTriggers(form))

const showNonExecutableWarning = computed(() =>
  !isTaskExecutableOnAe3(form.task_type, props.executableTaskTypes),
)

watch(intervalValue, syncIntervalSec)
watch(intervalUnit, syncIntervalSec)

watch([durationValue, durationUnit], () => {
  const multiplier = durationUnit.value === 'minutes' ? 60 : 1
  const raw = Math.round(durationValue.value * multiplier)
  if (!Number.isFinite(raw)) {
    return
  }
  const clamped = Math.min(
    MANUAL_SCHEDULE_LIMITS.durationSec.max,
    Math.max(MANUAL_SCHEDULE_LIMITS.durationSec.min, raw),
  )
  form.payload = { ...(form.payload ?? {}), duration_sec: clamped }
})

watch(runAtLocal, (value) => {
  if (!value) {
    form.run_at = undefined
    return
  }
  form.run_at = `${value}:00.000Z`
})

function toDatetimeLocalUtc(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

function syncIntervalSec(): void {
  const multiplier = intervalUnit.value === 'hours' ? 3600 : 60
  const raw = Math.round(intervalValue.value * multiplier)
  if (!Number.isFinite(raw)) {
    form.interval_sec = MANUAL_SCHEDULE_LIMITS.intervalSec.min
    return
  }
  form.interval_sec = Math.min(
    MANUAL_SCHEDULE_LIMITS.intervalSec.max,
    Math.max(MANUAL_SCHEDULE_LIMITS.intervalSec.min, raw),
  )
}

function fieldError(key: string): string | null {
  const messages = mergedErrors.value[key]
  return messages?.[0] ?? null
}

function taskCardClass(option: (typeof taskOptions)[number]): string {
  const selected = form.task_type === option.value
  const accentMap: Record<string, string> = {
    cyan: 'border-cyan-500/50 bg-cyan-500/10',
    amber: 'border-amber-500/50 bg-amber-500/10',
    green: 'border-emerald-500/50 bg-emerald-500/10',
    blue: 'border-sky-500/50 bg-sky-500/10',
    violet: 'border-violet-500/50 bg-violet-500/10',
    slate: 'border-slate-500/50 bg-slate-500/10',
  }
  return selected
    ? `${accentMap[option.accent] ?? 'border-[color:var(--accent-cyan)]'} ring-1 ring-[color:var(--accent-cyan)]/30`
    : 'border-[color:var(--border-muted)] hover:border-[color:var(--border-muted)]/80'
}

function toggleDay(day: number): void {
  const current = new Set(form.days_of_week ?? [])
  if (current.has(day)) {
    current.delete(day)
  } else {
    current.add(day)
  }
  form.days_of_week = Array.from(current).sort((a, b) => a - b)
}

function setDayPreset(preset: 'weekdays' | 'weekend' | 'all'): void {
  if (preset === 'weekdays') form.days_of_week = [1, 2, 3, 4, 5]
  if (preset === 'weekend') form.days_of_week = [6, 7]
  if (preset === 'all') form.days_of_week = []
}

function resetFormFromInitial(): void {
  localErrors.value = {}
  if (props.initial) {
    form.task_type = props.initial.task_type
    form.schedule_kind = props.initial.schedule_kind
    form.time_at = props.initial.time_at ?? '08:00'
    form.interval_sec = props.initial.interval_sec ?? 3600
    form.window_start = props.initial.window_start ?? '06:00'
    form.window_end = props.initial.window_end ?? '22:00'
    form.days_of_week = [...(props.initial.days_of_week ?? [])]
    form.label = props.initial.label ?? ''
    form.enabled = props.initial.enabled
    form.payload = { ...(props.initial.payload ?? {}) }
    if (props.initial.run_at) {
      runAtLocal.value = toDatetimeLocalUtc(props.initial.run_at)
      form.run_at = props.initial.run_at
    } else {
      runAtLocal.value = ''
      form.run_at = undefined
    }
  } else {
    form.task_type = 'irrigation'
    form.schedule_kind = 'time'
    form.time_at = '08:00'
    form.interval_sec = 3600
    form.window_start = '06:00'
    form.window_end = '22:00'
    form.days_of_week = []
    form.label = ''
    form.enabled = true
    form.payload = { duration_sec: 60 }
    runAtLocal.value = ''
    form.run_at = undefined
  }

  const interval = form.interval_sec ?? 3600
  if (interval % 3600 === 0) {
    intervalUnit.value = 'hours'
    intervalValue.value = interval / 3600
  } else {
    intervalUnit.value = 'minutes'
    intervalValue.value = Math.max(1, Math.round(interval / 60))
  }

  const duration = Number(form.payload?.duration_sec ?? 60)
  if (duration % 60 === 0 && duration >= 60) {
    durationUnit.value = 'minutes'
    durationValue.value = duration / 60
  } else {
    durationUnit.value = 'seconds'
    durationValue.value = duration
  }
}

watch(
  () => [props.open, props.initial] as const,
  () => {
    if (!props.open) return
    resetFormFromInitial()
  },
  { immediate: true },
)

watch(
  () => ({ ...form }),
  () => {
    localErrors.value = {}
    emit('clearServerErrors')
  },
  { deep: true },
)

function submit(): void {
  const errors = collectManualScheduleFormErrors(form, { isCreate: isCreate.value })
  if (Object.keys(errors).length > 0) {
    localErrors.value = errors
    return
  }
  localErrors.value = {}

  const payload: ZoneManualSchedulePayload = {
    task_type: form.task_type,
    schedule_kind: form.schedule_kind,
    label: form.label?.trim() || undefined,
    enabled: form.enabled,
    days_of_week: form.schedule_kind === 'once' ? undefined : (form.days_of_week ?? []),
    payload: form.task_type === 'irrigation'
      ? { duration_sec: Number(form.payload?.duration_sec ?? 60) }
      : {},
  }

  if (form.schedule_kind === 'time') {
    payload.time_at = normalizeTime(form.time_at)
  } else if (form.schedule_kind === 'interval') {
    payload.interval_sec = Number(form.interval_sec)
  } else if (form.schedule_kind === 'window') {
    payload.window_start = normalizeTime(form.window_start)
    payload.window_end = normalizeTime(form.window_end)
  } else if (form.schedule_kind === 'once') {
    payload.run_at = form.run_at
  }

  emit('submit', payload)
}

function normalizeTime(value?: string | null): string | undefined {
  if (!value) return undefined
  return value.length >= 5 ? value.slice(0, 5) : value
}
</script>
