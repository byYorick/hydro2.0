import type { EstopDeliveryStatus, ZoneEstopStatus } from '@/types/ZoneEstop'

export const ESTOP_ACTIVE_BANNER = 'Аварийная остановка активна, ручные команды заблокированы'

const STOP_SAFE_MANUAL_STEPS = new Set([
  'clean_fill_stop',
  'solution_fill_stop',
  'prepare_recirculation_stop',
  'irrigation_stop',
  'irrigation_recovery_stop',
  'solution_change_abort',
])

export function isEstopSafeManualStep(step: string): boolean {
  return STOP_SAFE_MANUAL_STEPS.has(step)
}

export function estopDeliveryMessage(status: ZoneEstopStatus | null | undefined): string {
  if (!status) return ''
  if (status.active) {
    if (status.stop_status === 'confirmed') return 'Отключение выходов подтверждено всеми узлами.'
    if (status.stop_status === 'failed') return 'Отключение выходов не подтверждено: ошибка команды. Повторите остановку.'
    return 'Ожидается подтверждение отключения выходов от узлов.'
  }
  if (status.release_status === 'pending') return 'Ожидается подтверждение снятия блокировки от узлов.'
  if (status.release_status === 'failed') return 'Узлы не подтвердили снятие блокировки. Повторите снятие.'
  return ''
}

export function estopResultMessage(result: string, status?: ZoneEstopStatus): string {
  const delivery = estopDeliveryMessage(status)
  if (delivery) return delivery
  switch (result) {
    case 'engaged':
      return 'Аварийная остановка включена. Ручные команды заблокированы.'
    case 'already_active':
      return 'Аварийная остановка уже включена.'
    case 'released':
      return 'Блокировка снята. Автоматическое восстановление выходов не выполняется.'
    case 'already_released':
      return 'Аварийная остановка уже снята.'
    default:
      return 'Состояние аварийной остановки обновлено.'
  }
}

export function formatSolutionLevelLabel(percent: number | null | undefined): string | null {
  if (percent === undefined) return null
  if (percent === null || !Number.isFinite(percent)) return 'Раствор: нет датчика'
  return `Раствор: ${Math.round(percent)}%`
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

export function readEstopStatus(payload: unknown): ZoneEstopStatus | null {
  const root = asRecord(payload)
  if (!root) return null
  const estop = asRecord(root.estop)
  if (!estop || typeof estop.active !== 'boolean') return null
  return {
    active: estop.active,
    stop_status: readDeliveryStatus(estop.stop_status),
    release_status: readDeliveryStatus(estop.release_status),
    source: typeof estop.source === 'string' ? estop.source : null,
    since: typeof estop.since === 'string' ? estop.since : null,
    node_uid: typeof estop.node_uid === 'string' ? estop.node_uid : null,
    event_id: typeof estop.event_id === 'number' ? estop.event_id : null,
  }
}

/**
 * `undefined` — уровня в ответе нет, подпись скрываем.
 * `null` — датчика раствора нет.
 */
export function readSolutionPercent(payload: unknown): number | null | undefined {
  const root = asRecord(payload)
  if (!root || !('tank_levels' in root)) return undefined
  const levels = asRecord(root.tank_levels)
  if (!levels) return null
  const value = levels.solution_percent
  if (typeof value === 'number' && Number.isFinite(value)) return value
  return null
}

function readDeliveryStatus(value: unknown): EstopDeliveryStatus | undefined {
  return value === 'not_requested' || value === 'pending' || value === 'confirmed' || value === 'failed' ? value : undefined
}
