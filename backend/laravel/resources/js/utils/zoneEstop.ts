import type { ZoneEstopStatus } from '@/types/ZoneEstop'

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

export function estopResultMessage(result: string): string {
  switch (result) {
    case 'engaged':
      return 'Аварийная остановка включена. Ручные команды заблокированы.'
    case 'already_active':
      return 'Аварийная остановка уже включена.'
    case 'released':
      return 'Аварийная остановка снята. Насосы и реле остаются выключенными.'
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
