import type { AutomationDocument } from '@/composables/useAutomationConfig'
import type { ProcessCalibrationMode, ZoneProcessCalibration, ZoneProcessCalibrationMeta } from '@/types/ProcessCalibration'

export const PROCESS_CALIBRATION_MODES: ProcessCalibrationMode[] = [
  'solution_fill',
  'tank_recirc',
  'irrigation',
  'generic',
]

const PROCESS_CALIBRATION_NAMESPACE_MAP: Record<ProcessCalibrationMode, string> = {
  generic: 'zone.process_calibration.generic',
  solution_fill: 'zone.process_calibration.solution_fill',
  tank_recirc: 'zone.process_calibration.tank_recirc',
  irrigation: 'zone.process_calibration.irrigation',
}

const PROCESS_CALIBRATION_SYNTHETIC_IDS: Record<ProcessCalibrationMode, number> = {
  generic: 4,
  solution_fill: 1,
  tank_recirc: 2,
  irrigation: 3,
}

function toNumberOrNull(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

function toStringOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function toMeta(value: unknown): ZoneProcessCalibrationMeta | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as ZoneProcessCalibrationMeta
}

export function processCalibrationNamespace(mode: ProcessCalibrationMode): string {
  return PROCESS_CALIBRATION_NAMESPACE_MAP[mode]
}

/**
 * Калибровка существует в authority-store (в том числе materialized system default).
 * Используется `ProcessCalibrationPanel` для отображения секции «Режим: X».
 */
export function isSavedProcessCalibration(calibration: ZoneProcessCalibration | null | undefined): boolean {
  return Boolean(calibration)
}

/**
 * Калибровка готова для боевого использования runtime'ом — т.е. это не
 * synthetic `system_default`, а реально сохранённая оператором/учёным
 * запись. Используется `CorrectionRuntimeReadinessCard` для fail-closed
 * проверки: system_default → fallback → runtime не должен дозировать.
 */
export function isRuntimeReadyProcessCalibration(
  calibration: ZoneProcessCalibration | null | undefined,
): boolean {
  if (!calibration) return false
  return calibration.source !== null
    && calibration.source !== undefined
    && calibration.source !== 'system_default'
}

export function documentToZoneProcessCalibration(
  zoneId: number,
  mode: ProcessCalibrationMode,
  document: AutomationDocument<Record<string, unknown>>,
): ZoneProcessCalibration {
  const payload = document.payload ?? {}

  return {
    id: zoneId * 10 + PROCESS_CALIBRATION_SYNTHETIC_IDS[mode],
    zone_id: zoneId,
    mode,
    ec_gain_per_ml: toNumberOrNull(payload.ec_gain_per_ml),
    ph_up_gain_per_ml: toNumberOrNull(payload.ph_up_gain_per_ml),
    ph_down_gain_per_ml: toNumberOrNull(payload.ph_down_gain_per_ml),
    ph_per_ec_ml: toNumberOrNull(payload.ph_per_ec_ml),
    ec_per_ph_ml: toNumberOrNull(payload.ec_per_ph_ml),
    transport_delay_sec: toNumberOrNull(payload.transport_delay_sec),
    settle_sec: toNumberOrNull(payload.settle_sec),
    confidence: toNumberOrNull(payload.confidence),
    source: toStringOrNull(payload.source),
    valid_from: toStringOrNull(payload.valid_from) ?? document.updated_at,
    valid_to: toStringOrNull(payload.valid_to),
    is_active: payload.is_active !== false,
    meta: toMeta(payload.meta),
  }
}
