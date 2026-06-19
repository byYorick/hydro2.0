import type {
  ManualScheduleKind,
  ManualSchedulePreviewTrigger,
  ZoneManualSchedulePayload,
} from '@/composables/zoneScheduleWorkspaceTypes'

const DAY_MS = 86_400_000

export const MANUAL_SCHEDULE_LIMITS = {
  durationSec: { min: 10, max: 86_400 },
  intervalSec: { min: 60, max: 86_400 },
} as const

function parseTimeToParts(time?: string | null): { hour: number; minute: number } | null {
  if (!time) return null
  const match = /^(\d{1,2}):(\d{2})/.exec(time.trim())
  if (!match) return null
  return { hour: Number(match[1]), minute: Number(match[2]) }
}

function matchesDayOfWeek(date: Date, daysOfWeek: number[]): boolean {
  if (!daysOfWeek.length) return true
  const iso = date.getUTCDay() === 0 ? 7 : date.getUTCDay()
  return daysOfWeek.includes(iso)
}

function utcDateAtTime(base: Date, hour: number, minute: number): Date {
  return new Date(Date.UTC(
    base.getUTCFullYear(),
    base.getUTCMonth(),
    base.getUTCDate(),
    hour,
    minute,
    0,
    0,
  ))
}

export function formatRelativeUtc(isoOrDate: string | Date, now = new Date()): string {
  const target = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate)
  if (Number.isNaN(target.getTime())) return '—'

  const diffMs = target.getTime() - now.getTime()
  if (Math.abs(diffMs) < 60_000) return 'сейчас'
  if (diffMs < 0) return 'прошло'

  const diffMin = Math.round(diffMs / 60_000)
  if (diffMin < 60) return `через ${diffMin} мин`

  const diffHours = Math.floor(diffMin / 60)
  const remainderMin = diffMin % 60
  if (diffHours < 48) {
    return remainderMin > 0 ? `через ${diffHours} ч ${remainderMin} мин` : `через ${diffHours} ч`
  }

  const diffDays = Math.round(diffHours / 24)
  return `через ${diffDays} д`
}

function formatUtcDateTime(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getUTCDate())}.${pad(date.getUTCMonth() + 1)} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`
}

export function buildManualScheduleSummary(form: ZoneManualSchedulePayload): string {
  const taskLabels: Record<string, string> = {
    irrigation: 'Полив',
    lighting: 'Свет',
    ventilation: 'Климат',
    mist: 'Туман',
    solution_change: 'Смена раствора',
    diagnostics: 'Диагностика',
  }
  const task = taskLabels[form.task_type] ?? form.task_type
  const dayLabels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
  const days = (form.days_of_week ?? [])
    .map((d) => dayLabels[d - 1])
    .filter(Boolean)
  const daysSuffix = days.length ? ` · ${days.join(', ')}` : ''

  if (form.schedule_kind === 'time' && form.time_at) {
    const duration = form.task_type === 'irrigation' && form.payload?.duration_sec
      ? ` · ${form.payload.duration_sec} с`
      : ''
    return `${task}${daysSuffix} в ${form.time_at}${duration}`
  }
  if (form.schedule_kind === 'interval' && form.interval_sec) {
    const interval = form.interval_sec % 3600 === 0
      ? `каждые ${form.interval_sec / 3600} ч`
      : form.interval_sec % 60 === 0
        ? `каждые ${form.interval_sec / 60} мин`
        : `каждые ${form.interval_sec} с`
    return `${task}${daysSuffix} · ${interval}`
  }
  if (form.schedule_kind === 'window') {
    return `${task}${daysSuffix} ${form.window_start ?? '—'}–${form.window_end ?? '—'}`
  }
  if (form.schedule_kind === 'once' && form.run_at) {
    const at = new Date(form.run_at)
    return `${task} · однократно ${formatUtcDateTime(at)}`
  }
  return task
}

export function previewManualScheduleTriggers(
  form: ZoneManualSchedulePayload,
  limit = 5,
  horizonHours = 168,
): ManualSchedulePreviewTrigger[] {
  if (form.enabled === false) {
    return []
  }

  const now = new Date()
  const horizonEnd = new Date(now.getTime() + horizonHours * 3_600_000)
  const days = form.days_of_week ?? []
  const candidates: Date[] = []

  if (form.schedule_kind === 'once' && form.run_at) {
    const runAt = new Date(form.run_at)
    if (runAt >= now && runAt <= horizonEnd) {
      candidates.push(runAt)
    }
  } else if (form.schedule_kind === 'time') {
    const parts = parseTimeToParts(form.time_at)
    if (parts) {
      for (let dayOffset = 0; dayOffset <= Math.ceil(horizonHours / 24); dayOffset++) {
        const base = new Date(now.getTime() + dayOffset * DAY_MS)
        if (!matchesDayOfWeek(base, days)) continue
        const candidate = utcDateAtTime(base, parts.hour, parts.minute)
        if (candidate >= now && candidate <= horizonEnd) {
          candidates.push(candidate)
        }
      }
    }
  } else if (form.schedule_kind === 'interval' && form.interval_sec && form.interval_sec >= MANUAL_SCHEDULE_LIMITS.intervalSec.min) {
    let cursor = new Date(now.getTime() + form.interval_sec * 1000)
    while (cursor <= horizonEnd && candidates.length < limit * 3) {
      if (matchesDayOfWeek(cursor, days)) {
        candidates.push(new Date(cursor))
      }
      cursor = new Date(cursor.getTime() + form.interval_sec * 1000)
    }
  } else if (form.schedule_kind === 'window') {
    const start = parseTimeToParts(form.window_start)
    const end = parseTimeToParts(form.window_end)
    if (start && end) {
      for (let dayOffset = 0; dayOffset <= Math.ceil(horizonHours / 24); dayOffset++) {
        const base = new Date(now.getTime() + dayOffset * DAY_MS)
        if (!matchesDayOfWeek(base, days)) continue
        for (const parts of [start, end]) {
          const candidate = utcDateAtTime(base, parts.hour, parts.minute)
          if (candidate >= now && candidate <= horizonEnd) {
            candidates.push(candidate)
          }
        }
      }
    }
  }

  candidates.sort((a, b) => a.getTime() - b.getTime())

  return candidates.slice(0, limit).map((at) => ({
    at: at.toISOString(),
    relativeLabel: formatRelativeUtc(at, now),
  }))
}

export function collectManualScheduleFormErrors(
  form: ZoneManualSchedulePayload,
  options?: { isCreate?: boolean },
): Record<string, string[]> {
  const errors: Record<string, string[]> = {}

  if (form.schedule_kind === 'time' && !form.time_at) {
    errors.time_at = ['Укажите время запуска.']
  }

  if (form.schedule_kind === 'interval') {
    const interval = Number(form.interval_sec ?? 0)
    if (!Number.isFinite(interval)) {
      errors.interval_sec = ['Укажите корректный интервал.']
    } else if (interval < MANUAL_SCHEDULE_LIMITS.intervalSec.min) {
      errors.interval_sec = [`Интервал не меньше ${MANUAL_SCHEDULE_LIMITS.intervalSec.min} с.`]
    } else if (interval > MANUAL_SCHEDULE_LIMITS.intervalSec.max) {
      errors.interval_sec = [`Интервал не больше ${MANUAL_SCHEDULE_LIMITS.intervalSec.max} с (24 ч).`]
    }
  }

  if (form.schedule_kind === 'window' && (!form.window_start || !form.window_end)) {
    errors.window_start = ['Укажите начало и конец окна.']
  }

  if (form.schedule_kind === 'once') {
    if (!form.run_at) {
      errors.run_at = ['Укажите дату и время.']
    } else if (options?.isCreate && new Date(form.run_at).getTime() <= Date.now()) {
      errors.run_at = ['Для разового расписания укажите время в будущем (UTC).']
    }
  }

  if (form.task_type === 'irrigation') {
    const duration = Number(form.payload?.duration_sec ?? 0)
    if (!Number.isFinite(duration)) {
      errors['payload.duration_sec'] = ['Укажите корректную длительность.']
    } else if (duration < MANUAL_SCHEDULE_LIMITS.durationSec.min || duration > MANUAL_SCHEDULE_LIMITS.durationSec.max) {
      errors['payload.duration_sec'] = [
        `Длительность от ${MANUAL_SCHEDULE_LIMITS.durationSec.min} до ${MANUAL_SCHEDULE_LIMITS.durationSec.max} с.`,
      ]
    }
  }

  return errors
}

export function isManualScheduleFormValid(
  form: ZoneManualSchedulePayload,
  options?: { isCreate?: boolean },
): boolean {
  return Object.keys(collectManualScheduleFormErrors(form, options)).length === 0
}

export function toManualSchedulePayload(schedule: {
  task_type: ZoneManualSchedulePayload['task_type']
  schedule_kind: ManualScheduleKind
  time_at?: string | null
  interval_sec?: number | null
  window_start?: string | null
  window_end?: string | null
  days_of_week?: number[]
  run_at?: string | null
  payload?: Record<string, unknown>
  label?: string | null
  enabled?: boolean
}): ZoneManualSchedulePayload {
  return {
    task_type: schedule.task_type,
    schedule_kind: schedule.schedule_kind,
    time_at: schedule.time_at ?? undefined,
    interval_sec: schedule.interval_sec ?? undefined,
    window_start: schedule.window_start ?? undefined,
    window_end: schedule.window_end ?? undefined,
    days_of_week: schedule.days_of_week,
    run_at: schedule.run_at ?? undefined,
    payload: schedule.payload as ZoneManualSchedulePayload['payload'],
    label: schedule.label ?? undefined,
    enabled: schedule.enabled,
  }
}

export const MANUAL_SCHEDULE_TASK_OPTIONS: Array<{
  value: ZoneManualSchedulePayload['task_type']
  label: string
  hint: string
  accent: string
}> = [
  { value: 'irrigation', label: 'Полив', hint: 'Насос полива', accent: 'cyan' },
  { value: 'lighting', label: 'Свет', hint: 'Освещение', accent: 'amber' },
  { value: 'ventilation', label: 'Климат', hint: 'Вентиляция', accent: 'green' },
  { value: 'mist', label: 'Туман', hint: 'Увлажнение', accent: 'blue' },
  { value: 'solution_change', label: 'Смена раствора', hint: 'Обслуживание', accent: 'violet' },
  { value: 'diagnostics', label: 'Диагностика', hint: 'Проверка цикла', accent: 'slate' },
]

export const MANUAL_SCHEDULE_KIND_OPTIONS: Array<{ value: ManualScheduleKind; label: string }> = [
  { value: 'time', label: 'Время' },
  { value: 'interval', label: 'Интервал' },
  { value: 'window', label: 'Окно' },
  { value: 'once', label: 'Разово' },
]

export const WEEKDAY_OPTIONS = [
  { value: 1, label: 'Пн' },
  { value: 2, label: 'Вт' },
  { value: 3, label: 'Ср' },
  { value: 4, label: 'Чт' },
  { value: 5, label: 'Пт' },
  { value: 6, label: 'Сб' },
  { value: 7, label: 'Вс' },
]

export function isTaskExecutableOnAe3(
  taskType: string,
  executableTaskTypes: string[],
): boolean {
  const publicType = taskType === 'ventilation' ? 'climate' : taskType
  return executableTaskTypes.includes(publicType) || executableTaskTypes.includes(taskType)
}
