import { classifyEventKind, translateEventKind } from '@/utils/i18n'
import { groupZoneEvents } from '@/utils/eventGroups'
import {
  firstNumber,
  firstString,
  formatPayloadNumber,
  readNumber,
  readString,
  toPayloadRecord,
} from '@/utils/eventPayload'
import type { ZoneEvent } from '@/types/ZoneEvent'

export type OperatorStorySeverity = 'alert' | 'warning' | 'info' | 'action' | 'success'

export interface OperatorStoryStep {
  label: string
  at: string
  eventIds: number[]
}

export interface OperatorStory {
  id: string
  title: string
  summary: string
  severity: OperatorStorySeverity
  occurredAt: string
  eventIds: number[]
  steps: OperatorStoryStep[]
  collapsedNoise?: { label: string; count: number; eventIds: number[] }[]
}

export type CollapsedFeedItem =
  | { type: 'event'; event: ZoneEvent }
  | {
      type: 'collapsed'
      kind: string
      label: string
      count: number
      events: ZoneEvent[]
      latestOccurredAt: string
    }

const ENGINEER_ONLY_KINDS = new Set([
  'IRR_STATE_SNAPSHOT',
  'PID_OUTPUT',
  'command_status',
  'COMMAND_STATUS',
  'LEVEL_SWITCH_CHANGED',
  'CORRECTION_SKIPPED_COOLDOWN',
  'CORRECTION_SKIPPED_DOSE_DISCARDED',
  'CORRECTION_SKIPPED_FRESHNESS',
  'CORRECTION_SKIPPED_WINDOW_NOT_READY',
  'CORRECTION_SKIPPED_WATER_LEVEL',
  'CORRECTION_SKIPPED_DEAD_ZONE',
  'CORRECTION_OBSERVATION_EVALUATED',
])

const ENGINEER_ONLY_PREFIXES = ['CORRECTION_SKIPPED_'] as const

const OPERATOR_VISIBLE_SKIPPED = new Set([
  'CORRECTION_SKIPPED_EMERGENCY_STOP',
  'CORRECTION_SKIPPED_BY_ALERT_BLOCK',
])

const COLLAPSE_KINDS = new Set([
  'IRR_STATE_SNAPSHOT',
  'PID_OUTPUT',
  'command_status',
  'COMMAND_STATUS',
  'LEVEL_SWITCH_CHANGED',
  'AE_TASK_STARTED',
])

function eventTime(event: ZoneEvent): string {
  return event.occurred_at ?? event.created_at ?? ''
}

function parseTime(value: string | undefined): number {
  if (!value) return 0
  const ts = Date.parse(value)
  return Number.isFinite(ts) ? ts : 0
}

function severityFromKind(kind: string): OperatorStorySeverity {
  const category = classifyEventKind(kind)
  if (category === 'ALERT' || kind === 'AE_TASK_FAILED' || kind === 'COMMAND_TIMEOUT') {
    return 'alert'
  }
  if (category === 'WARNING' || kind.includes('SKIPPED') || kind.includes('NO_EFFECT')) {
    return 'warning'
  }
  if (category === 'ACTION' || kind.includes('DOSING') || kind.includes('CORRECTED')) {
    return 'action'
  }
  if (kind.includes('COMPLETE') || kind.includes('FINISHED') || kind.includes('DONE')) {
    return 'success'
  }
  return 'info'
}

function maxSeverity(a: OperatorStorySeverity, b: OperatorStorySeverity): OperatorStorySeverity {
  const rank: Record<OperatorStorySeverity, number> = {
    alert: 4,
    warning: 3,
    action: 2,
    success: 1,
    info: 0,
  }
  return rank[a] >= rank[b] ? a : b
}

/** События, которые по умолчанию не показывают оператору как отдельные карточки. */
export function isEngineerOnlyEvent(event: ZoneEvent): boolean {
  const kind = event.kind ?? ''
  if (OPERATOR_VISIBLE_SKIPPED.has(kind)) return false
  if (ENGINEER_ONLY_KINDS.has(kind)) return true
  if (kind === 'COMMAND_TIMEOUT') return false
  if (ENGINEER_ONLY_PREFIXES.some((prefix) => kind.startsWith(prefix))) return true
  return false
}

/** Человеческая однострочная сводка по одному событию. */
export function summarizeEventForOperator(event: ZoneEvent): string {
  const payload = toPayloadRecord(event.payload)
  const kind = event.kind ?? ''

  if (kind === 'ALERT_CREATED' || kind.startsWith('ALERT_')) {
    const code = firstString(payload, ['code', 'error_code', 'message'])
    return code ? `Тревога: ${code}` : (event.message || 'Тревога')
  }

  if (kind === 'COMMAND_TIMEOUT') {
    const cmd = firstString(payload, ['cmd', 'command', 'cmd_id']) ?? 'команда'
    return `Тревога: таймаут — ${cmd}`
  }

  if (kind === 'AE_TASK_FAILED') {
    const err = firstString(payload, ['error_code', 'error_message']) ?? 'ошибка задачи'
    return `Тревога: ${err}`
  }

  if (kind === 'IRRIGATION_CYCLE_STARTED' || kind === 'IRRIGATION_START') {
    return 'Полив начат'
  }
  if (kind === 'IRRIGATION_CYCLE_FINISHED') {
    return 'Полив завершён'
  }
  if (kind === 'IRRIGATION_CYCLE_STOPPED' || kind === 'IRRIGATION_STOP') {
    return 'Полив остановлен'
  }
  if (kind === 'IRRIGATION_CYCLE_SKIPPED') {
    return 'Полив пропущен'
  }

  if (kind === 'IRRIGATION_DECISION_EVALUATED') {
    const outcome = readString(payload, 'outcome')
    if (outcome === 'run' || outcome === 'start') return 'Решение: полив разрешён'
    if (outcome === 'skip') return 'Решение: полив пропущен'
    if (outcome === 'degraded_run') return 'Решение: деградированный полив'
    return outcome ? `Решение о поливе: ${outcome}` : 'Решение о поливе'
  }

  if (kind === 'CORRECTION_DECISION_MADE') {
    const action = readString(payload, 'selected_action')
    const ph = formatPayloadNumber(firstNumber(payload, ['current_ph', 'ph']), 2)
    const ec = formatPayloadNumber(firstNumber(payload, ['current_ec', 'ec']), 2)
    if (action?.startsWith('ec') || action === 'ec') {
      return ph || ec
        ? `EC вне цели${ec ? ` (${ec})` : ''} → дозирование`
        : 'EC вне цели → дозирование'
    }
    if (action?.includes('ph')) {
      return `pH вне цели${ph ? ` (${ph})` : ''} → коррекция`
    }
    return action ? `Решение коррекции: ${action}` : 'Решение коррекции'
  }

  if (kind === 'EC_DOSING' || kind === 'IRRIGATION_EC_MULTI_DOSE') {
    const ml = formatPayloadNumber(firstNumber(payload, ['dose_ml', 'total_dose_ml', 'effective_ml']), 1)
    const channel = firstString(payload, ['channel', 'component', 'components'])
    if (ml && channel) return `Дозирование ${channel} ${ml} мл`
    if (ml) return `Дозирование A+B ${ml} мл`
    return 'Дозирование EC'
  }

  if (kind === 'PH_CORRECTED') {
    const ml = formatPayloadNumber(firstNumber(payload, ['dose_ml', 'effective_ml']), 1)
    const action = readString(payload, 'selected_action') ?? 'pH'
    return ml ? `${action}: ${ml} мл` : `Коррекция ${action}`
  }

  if (kind === 'IRRIGATION_CORRECTION_STARTED') {
    return 'Коррекция во время полива'
  }

  if (kind === 'CORRECTION_COMPLETE' || kind === 'IRRIGATION_CORRECTION_COMPLETED') {
    return 'Коррекция завершена'
  }

  if (kind === 'CORRECTION_EXHAUSTED') {
    return 'Коррекция исчерпана'
  }

  if (kind === 'CORRECTION_NO_EFFECT') {
    return 'Коррекция без эффекта — ожидание'
  }

  if (kind.includes('OBSERVATION') || kind === 'CORRECTION_ACTION_DEFERRED') {
    return 'Ожидание'
  }

  if (event.message && event.message.trim().length > 0 && event.message.length < 120) {
    return event.message
  }

  return translateEventKind(kind)
}

function buildStorySummary(eventsAsc: ZoneEvent[]): string {
  const labels = eventsAsc
    .filter((event) => !isEngineerOnlyEvent(event))
    .map((event) => summarizeEventForOperator(event))

  const unique: string[] = []
  labels.forEach((label) => {
    if (unique[unique.length - 1] !== label) unique.push(label)
  })

  if (unique.length === 0) return 'Событие зоны'
  if (unique.length === 1) return unique[0]
  return unique.slice(0, 4).join(' → ')
}

function buildStoryTitle(events: ZoneEvent[], fallback: string): string {
  const kinds = new Set(events.map((event) => event.kind))
  if ([...kinds].some((kind) => kind.startsWith('ALERT') || kind === 'COMMAND_TIMEOUT' || kind === 'AE_TASK_FAILED')) {
    return 'Тревога'
  }
  if ([...kinds].some((kind) => kind.includes('IRRIGATION_CYCLE') || kind === 'IRRIGATION_START' || kind === 'IRRIGATION_STOP')) {
    return 'Полив'
  }
  if ([...kinds].some((kind) => kind.includes('CORRECTION') || kind.includes('DOSING') || kind === 'PH_CORRECTED' || kind === 'EC_DOSING')) {
    for (const event of events) {
      const payload = toPayloadRecord(event.payload)
      const action = readString(payload, 'selected_action')
      if (action?.includes('ph')) return 'Коррекция pH'
      if (action?.startsWith('ec') || action === 'ec') return 'Коррекция EC'
    }
    if ([...kinds].some((kind) => kind === 'EC_DOSING' || kind === 'IRRIGATION_EC_MULTI_DOSE')) {
      return 'Коррекция EC'
    }
    if (kinds.has('PH_CORRECTED')) return 'Коррекция pH'
    return 'Коррекция раствора'
  }
  return fallback || 'Событие'
}

function collectCollapsedNoise(allEvents: ZoneEvent[], storyEventIds: Set<number>): OperatorStory['collapsedNoise'] {
  const related = allEvents.filter((event) => {
    if (!isEngineerOnlyEvent(event)) return false
    const payload = toPayloadRecord(event.payload)
    const taskId = readNumber(payload, 'task_id')
    const windowId = readString(payload, 'correction_window_id')
    if (!windowId && taskId === null) return false
    // Привязка шума к story по совпадению task/window среди story events
    return [...storyEventIds].some((id) => {
      const storyEvent = allEvents.find((item) => item.id === id)
      if (!storyEvent) return false
      const storyPayload = toPayloadRecord(storyEvent.payload)
      const storyTask = readNumber(storyPayload, 'task_id')
      const storyWindow = readString(storyPayload, 'correction_window_id')
      return (windowId && storyWindow && windowId === storyWindow)
        || (taskId !== null && storyTask !== null && taskId === storyTask)
    })
  })

  if (related.length === 0) return undefined

  const byKind = new Map<string, ZoneEvent[]>()
  related.forEach((event) => {
    const list = byKind.get(event.kind) ?? []
    list.push(event)
    byKind.set(event.kind, list)
  })

  return [...byKind.entries()].map(([kind, events]) => ({
    label: translateEventKind(kind),
    count: events.length,
    eventIds: events.map((event) => event.id),
  }))
}

/** Построить операторские истории из ленты событий. */
export function buildOperatorStories(events: ZoneEvent[]): OperatorStory[] {
  const list = Array.isArray(events) ? events : []
  const operatorEvents = list.filter((event) => !isEngineerOnlyEvent(event))
  const groups = groupZoneEvents(operatorEvents)

  return groups.map((group) => {
    const chronological = [...group.events].sort((left, right) => {
      const timeDiff = parseTime(eventTime(left)) - parseTime(eventTime(right))
      if (timeDiff !== 0) return timeDiff
      return left.id - right.id
    })

    const steps: OperatorStoryStep[] = chronological.map((event) => ({
      label: summarizeEventForOperator(event),
      at: eventTime(event),
      eventIds: [event.id],
    }))

    const eventIds = group.events.map((event) => event.id)
    const severity = chronological.reduce<OperatorStorySeverity>(
      (acc, event) => maxSeverity(acc, severityFromKind(event.kind)),
      'info',
    )

    return {
      id: group.id,
      title: buildStoryTitle(group.events, group.title),
      summary: buildStorySummary(chronological),
      severity,
      occurredAt: group.latestOccurredAt,
      eventIds,
      steps,
      collapsedNoise: collectCollapsedNoise(list, new Set(eventIds)),
    }
  })
}

/** Схлопнуть подряд идущие шумные события для инженерного лога. */
export function collapseNoisyEvents(events: ZoneEvent[]): CollapsedFeedItem[] {
  const sorted = [...(Array.isArray(events) ? events : [])].sort((left, right) => {
    const timeDiff = parseTime(eventTime(right)) - parseTime(eventTime(left))
    if (timeDiff !== 0) return timeDiff
    return right.id - left.id
  })

  const result: CollapsedFeedItem[] = []

  for (const event of sorted) {
    const last = result[result.length - 1]
    if (
      COLLAPSE_KINDS.has(event.kind)
      && last
      && last.type === 'collapsed'
      && last.kind === event.kind
    ) {
      last.events.push(event)
      last.count = last.events.length
      last.label = `${last.count}× ${translateEventKind(event.kind)}`
      if (parseTime(eventTime(event)) > parseTime(last.latestOccurredAt)) {
        last.latestOccurredAt = eventTime(event)
      }
      continue
    }

    if (
      COLLAPSE_KINDS.has(event.kind)
      && last
      && last.type === 'event'
      && last.event.kind === event.kind
    ) {
      const pair = [last.event, event]
      result[result.length - 1] = {
        type: 'collapsed',
        kind: event.kind,
        label: `2× ${translateEventKind(event.kind)}`,
        count: 2,
        events: pair,
        latestOccurredAt: parseTime(eventTime(event)) >= parseTime(eventTime(last.event))
          ? eventTime(event)
          : eventTime(last.event),
      }
      continue
    }

    if (COLLAPSE_KINDS.has(event.kind)) {
      // одиночный шум пока как обычное событие; схлопнется при втором
      result.push({ type: 'event', event })
      continue
    }

    result.push({ type: 'event', event })
  }

  return result
}

/** Список kind, исключаемых сервером для audience=operator (зеркало isEngineerOnly). */
export const OPERATOR_EXCLUDED_KINDS = [
  'IRR_STATE_SNAPSHOT',
  'PID_OUTPUT',
  'command_status',
  'COMMAND_STATUS',
  'LEVEL_SWITCH_CHANGED',
  'CORRECTION_SKIPPED_COOLDOWN',
  'CORRECTION_SKIPPED_DOSE_DISCARDED',
  'CORRECTION_SKIPPED_FRESHNESS',
  'CORRECTION_SKIPPED_WINDOW_NOT_READY',
  'CORRECTION_SKIPPED_WATER_LEVEL',
  'CORRECTION_SKIPPED_DEAD_ZONE',
  'CORRECTION_OBSERVATION_EVALUATED',
] as const
