import { computed, ref, watch, type Ref } from 'vue'
import { api } from '@/services/api'
import { automationConfigsApi } from '@/services/api/automationConfigs'
import type { PidConfig, PumpCalibration } from '@/types/PidConfig'
import { logger } from '@/utils/logger'

export type CorrectionPumpController = 'ph' | 'ec'

export interface CorrectionPumpHoverInfo {
  channel: string
  controller: CorrectionPumpController
  component: string | null
  node_uid: string | null
  ml_per_sec: number | null
  k_ms_per_ml_l: number | null
  kp: number | null
  ki: number | null
  kd: number | null
  dead_zone: number | null
  max_dose_ml: number | null
  min_interval_sec: number | null
}

const PH_CHANNELS = new Set(['pump_acid', 'pump_base'])
const EC_CHANNELS = new Set(['pump_a', 'pump_b', 'pump_c', 'pump_d'])
const ALL_CHANNELS = [...PH_CHANNELS, ...EC_CHANNELS]

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function readNumber(value: unknown): number | null {
  if (value == null || value === '') {
    return null
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function extractPidPayload(raw: unknown): PidConfig | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }
  const source = raw as Record<string, unknown>
  const payload = source.payload && typeof source.payload === 'object'
    ? source.payload as Record<string, unknown>
    : source
  if (!payload.zone_coeffs || typeof payload.zone_coeffs !== 'object') {
    return null
  }
  return payload as unknown as PidConfig
}

function extractControllerLimits(
  correctionDoc: unknown,
  controller: CorrectionPumpController,
): { max_dose_ml: number | null, min_interval_sec: number | null } {
  const source = asRecord(correctionDoc)
  const resolved = asRecord(source.resolved_config)
  const base = asRecord(resolved.base ?? source.base_config ?? source.payload)
  const controllers = asRecord(base.controllers)
  const cfg = asRecord(controllers[controller])
  return {
    max_dose_ml: readNumber(cfg.max_dose_ml),
    min_interval_sec: readNumber(cfg.min_interval_sec),
  }
}

function controllerForChannel(channel: string): CorrectionPumpController {
  return PH_CHANNELS.has(channel) ? 'ph' : 'ec'
}

function formatNum(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) {
    return '—'
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(digits).replace(/\.?0+$/, '')
}

/** Tooltip rows for a dosing pump on the process diagram. */
export function buildCorrectionPumpHoverData(
  info: CorrectionPumpHoverInfo | null | undefined,
): Record<string, string> {
  if (!info) {
    return {
      'Калибровка': 'нет данных',
      'PID': 'нет данных',
    }
  }
  return {
    'Компонент': info.component ?? '—',
    'Узел': info.node_uid ?? '—',
    'мл/с': formatNum(info.ml_per_sec, 4),
    'k мс/(мл·л)': formatNum(info.k_ms_per_ml_l, 4),
    'PID (close)': `Kp=${formatNum(info.kp)} Ki=${formatNum(info.ki)} Kd=${formatNum(info.kd)}`,
    'dead_zone': formatNum(info.dead_zone),
    'max_dose_ml': formatNum(info.max_dose_ml, 2),
    'min_interval_s': formatNum(info.min_interval_sec, 0),
  }
}

export function useCorrectionPumpHoverData(
  zoneId: Ref<number | null | undefined>,
  refreshSeq: Ref<number> = ref(0),
) {
  const byChannel = ref<Record<string, CorrectionPumpHoverInfo>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(): Promise<void> {
    const id = Number(zoneId.value)
    if (!Number.isFinite(id) || id <= 0) {
      byChannel.value = {}
      return
    }

    loading.value = true
    error.value = null
    try {
      const [calibrationsRaw, pidPhRaw, pidEcRaw, correctionRaw] = await Promise.all([
        api.zones.getPumpCalibrations<PumpCalibration[] | { data?: PumpCalibration[] }>(id),
        automationConfigsApi.get('zone', id, 'zone.pid.ph').catch(() => null),
        automationConfigsApi.get('zone', id, 'zone.pid.ec').catch(() => null),
        automationConfigsApi.get('zone', id, 'zone.correction').catch(() => null),
      ])

      const calibrations = Array.isArray(calibrationsRaw)
        ? calibrationsRaw
        : (Array.isArray(calibrationsRaw?.data) ? calibrationsRaw.data : [])

      const pidByController: Record<CorrectionPumpController, PidConfig | null> = {
        ph: extractPidPayload(pidPhRaw),
        ec: extractPidPayload(pidEcRaw),
      }
      const limitsByController: Record<CorrectionPumpController, {
        max_dose_ml: number | null
        min_interval_sec: number | null
      }> = {
        ph: extractControllerLimits(correctionRaw, 'ph'),
        ec: extractControllerLimits(correctionRaw, 'ec'),
      }

      const calByChannel = new Map<string, PumpCalibration>()
      for (const row of calibrations) {
        const channel = String(row.channel || row.role || '').trim().toLowerCase()
        if (!channel || !ALL_CHANNELS.includes(channel)) {
          continue
        }
        calByChannel.set(channel, row)
      }

      const next: Record<string, CorrectionPumpHoverInfo> = {}
      for (const channel of ALL_CHANNELS) {
        const controller = controllerForChannel(channel)
        const pid = pidByController[controller]
        const close = pid?.zone_coeffs?.close
        const cal = calByChannel.get(channel)
        const limits = limitsByController[controller]
        next[channel] = {
          channel,
          controller,
          component: cal?.component ?? null,
          node_uid: cal?.node_uid ?? null,
          ml_per_sec: cal?.ml_per_sec ?? null,
          k_ms_per_ml_l: cal?.k_ms_per_ml_l ?? null,
          kp: close?.kp ?? null,
          ki: close?.ki ?? null,
          kd: close?.kd ?? null,
          dead_zone: pid?.dead_zone ?? null,
          max_dose_ml: limits.max_dose_ml,
          min_interval_sec: limits.min_interval_sec,
        }
      }
      byChannel.value = next
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Не удалось загрузить PID/калибровки'
      logger.warn('[useCorrectionPumpHoverData] load failed', { zoneId: id, err })
      byChannel.value = {}
    } finally {
      loading.value = false
    }
  }

  watch(
    [zoneId, refreshSeq],
    () => {
      void load()
    },
    { immediate: true },
  )

  const pumpHoverByChannel = computed(() => byChannel.value)

  return {
    pumpHoverByChannel,
    loading,
    error,
    reload: load,
  }
}
