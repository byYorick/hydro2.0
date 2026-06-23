/**
 * Zones domain API client.
 *
 * Все HTTP-запросы к `/api/zones/*` ДОЛЖНЫ идти через этот модуль.
 * Composables/stores импортируют `api.zones`, а не `apiClient` напрямую.
 */
import type { Zone } from '@/types'
import { normalizePaginatedList } from '@/utils/apiHelpers'
import type { PumpCalibrationRunPayload, PumpCalibrationSavePayload } from '@/types/Calibration'
import type {
  SensorCalibration,
  SensorCalibrationOverview,
  SensorCalibrationStartResult,
} from '@/types/SensorCalibration'
import type { ZoneManualSchedulePayload } from '@/composables/zoneScheduleWorkspaceTypes'
import { apiGet, apiPost, apiPostVoid, apiPut, apiDelete } from './_client'

export interface ZoneCreatePayload {
  name: string
  description?: string
  status?: string
  greenhouse_id?: number | null
  [key: string]: unknown
}

export interface ZonesListParams {
  search?: string
  [key: string]: string | number | boolean | undefined
}

export const zonesApi = {
  /**
   * Список всех зон текущего пользователя/теплицы.
   */
  async list(params?: ZonesListParams): Promise<Zone[]> {
    const response = await apiGet<unknown>('/zones', { params })
    return normalizePaginatedList<Zone>(response)
  },

  /**
   * Детальная информация о зоне по ID.
   */
  getById(zoneId: number): Promise<Zone> {
    return apiGet<Zone>(`/zones/${zoneId}`)
  },

  /**
   * Создать новую зону.
   */
  create(payload: ZoneCreatePayload): Promise<Zone> {
    return apiPost<Zone>('/zones', payload)
  },

  /**
   * Неназначенные ошибки нод в контексте зоны.
   */
  unassignedErrors(
    zoneId: number,
    params?: Record<string, unknown>,
  ): Promise<{ data: unknown[]; meta?: Record<string, unknown> }> {
    return apiGet<{ data: unknown[]; meta?: Record<string, unknown> }>(
      `/zones/${zoneId}/unassigned-errors`,
      { params },
    )
  },

  /**
   * История команд зоны (пагинация, фильтр по status).
   */
  commands(
    zoneId: number,
    params?: Record<string, unknown>,
  ): Promise<{ data: unknown[]; meta?: Record<string, unknown> }> {
    return apiGet<{ data: unknown[]; meta?: Record<string, unknown> }>(
      `/zones/${zoneId}/commands`,
      { params },
    )
  },

  /**
   * Effective targets для зоны (читаются из active recipe phase).
   */
  effectiveTargets(zoneId: number): Promise<Record<string, unknown>> {
    return apiGet<Record<string, unknown>>(`/zones/${zoneId}/effective-targets`)
  },

  /**
   * Текущий grow cycle для зоны.
   */
  getGrowCycle(zoneId: number): Promise<{ id?: number } & Record<string, unknown>> {
    return apiGet<{ id?: number } & Record<string, unknown>>(`/zones/${zoneId}/grow-cycle`)
  },

  createGrowCycle<T = unknown>(zoneId: number, payload: Record<string, unknown>): Promise<T> {
    return apiPost<T>(`/zones/${zoneId}/grow-cycles`, payload)
  },

  /**
   * Zone events (audit-лог коррекций, калибровок и команд).
   * Backend отдаёт `{ status, data: ZoneEvent[], meta }`, поэтому
   * возвращаем необёрнутый массив (apiGet уже снимет верхний `data` wrapper).
   */
  events(zoneId: number, params?: Record<string, unknown>): Promise<unknown> {
    return apiGet<unknown>(`/zones/${zoneId}/events`, { params })
  },

  /**
   * Подробная детализация зоны (для PidConfigForm и прочих consumer'ов).
   */
  getDetail(zoneId: number): Promise<Record<string, unknown>> {
    return apiGet<Record<string, unknown>>(`/zones/${zoneId}`)
  },

  /**
   * Запуск штатного/форсированного полива зоны.
   */
  startIrrigation(
    zoneId: number,
    payload: { mode: 'normal' | 'force'; source?: string; requested_duration_sec?: number | null },
  ): Promise<void> {
    return apiPostVoid(`/zones/${zoneId}/start-irrigation`, payload)
  },

  /**
   * Запуск диагностического цикла AE3 (cycle_start / DIAGNOSTICS_TICK).
   */
  startCycle(
    zoneId: number,
    payload?: { source?: string; idempotency_key?: string },
  ): Promise<Record<string, unknown>> {
    return apiPost<Record<string, unknown>>(`/zones/${zoneId}/start-cycle`, payload ?? {})
  },

  /**
   * Запуск / сохранение калибровки насоса. Возвращает `run_token` при запуске.
   */
  calibratePump(
    zoneId: number,
    payload: PumpCalibrationRunPayload | (PumpCalibrationSavePayload & { skip_run?: boolean }),
  ): Promise<{ run_token?: string } & Record<string, unknown>> {
    return apiPost<{ run_token?: string } & Record<string, unknown>>(
      `/zones/${zoneId}/calibrate-pump`,
      payload,
    )
  },

  // ─── Sensor calibrations ─────────────────────────────────────────────────
  sensorCalibrationStatus(zoneId: number): Promise<SensorCalibrationOverview[]> {
    return apiGet<SensorCalibrationOverview[]>(`/zones/${zoneId}/sensor-calibrations/status`)
  },

  sensorCalibrationsList(zoneId: number, params?: Record<string, unknown>): Promise<SensorCalibration[]> {
    return apiGet<SensorCalibration[]>(`/zones/${zoneId}/sensor-calibrations`, { params })
  },

  sensorCalibration(zoneId: number, calibrationId: number): Promise<SensorCalibration> {
    return apiGet<SensorCalibration>(`/zones/${zoneId}/sensor-calibrations/${calibrationId}`)
  },

  sensorCalibrationStart(
    zoneId: number,
    payload: { node_channel_id: number; sensor_type: 'ph' | 'ec' },
  ): Promise<SensorCalibrationStartResult> {
    return apiPost<SensorCalibrationStartResult>(`/zones/${zoneId}/sensor-calibrations`, payload)
  },

  sensorCalibrationAddPoint(
    zoneId: number,
    calibrationId: number,
    payload: { stage: 1 | 2; reference_value: number },
  ): Promise<SensorCalibration> {
    return apiPost<SensorCalibration>(
      `/zones/${zoneId}/sensor-calibrations/${calibrationId}/point`,
      payload,
    )
  },

  sensorCalibrationCancel(zoneId: number, calibrationId: number): Promise<void> {
    return apiPostVoid(`/zones/${zoneId}/sensor-calibrations/${calibrationId}/cancel`, {})
  },

  // ─── Scheduler workspace ─────────────────────────────────────────────────
  scheduleWorkspace<T = unknown>(zoneId: number, params?: Record<string, unknown>): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/schedule-workspace`, { params })
  },

  getState<T = unknown>(zoneId: number): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/state`)
  },

  getHealth<T = unknown>(zoneId: number): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/health`)
  },

  getSnapshot<T = unknown>(zoneId: number): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/snapshot`)
  },

  getExecution<T = unknown>(zoneId: number, executionId: string): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/executions/${encodeURIComponent(executionId)}`)
  },

  retryExecution<T = unknown>(zoneId: number, executionId: string): Promise<T> {
    return apiPost<T>(`/zones/${zoneId}/executions/${encodeURIComponent(executionId)}/retry`, {})
  },

  schedulerDiagnostics<T = unknown>(zoneId: number): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/scheduler-diagnostics`)
  },

  createManualSchedule<T = unknown>(
    zoneId: number,
    payload: ZoneManualSchedulePayload,
  ): Promise<T> {
    return apiPost<T>(`/zones/${zoneId}/manual-schedules`, payload, { skipErrorToast: true })
  },

  updateManualSchedule<T = unknown>(
    zoneId: number,
    scheduleId: number,
    payload: Partial<ZoneManualSchedulePayload>,
  ): Promise<T> {
    return apiPut<T>(`/zones/${zoneId}/manual-schedules/${scheduleId}`, payload, { skipErrorToast: true })
  },

  deleteManualSchedule(zoneId: number, scheduleId: number): Promise<void> {
    return apiDelete<void>(`/zones/${zoneId}/manual-schedules/${scheduleId}`, { skipErrorToast: true })
  },

  // ─── Control mode / manual steps ─────────────────────────────────────────
  getControlMode<T = unknown>(zoneId: number): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/control-mode`)
  },

  setControlMode<T = unknown>(
    zoneId: number,
    payload: { control_mode: string; source?: string; reason?: string },
  ): Promise<T> {
    return apiPost<T>(`/zones/${zoneId}/control-mode`, payload)
  },

  runManualStep(
    zoneId: number,
    payload: { manual_step: string; source?: string },
  ): Promise<unknown> {
    return apiPost<unknown>(`/zones/${zoneId}/manual-step`, payload)
  },

  // ─── PID / pump calibration / relay autotune ────────────────────────────
  getPidLogs<T = unknown>(
    zoneId: number,
    params?: { type?: string; limit?: number; offset?: number },
  ): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/pid-logs`, { params })
  },

  getPumpCalibrations<T = unknown>(zoneId: number): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/pump-calibrations`)
  },

  updatePumpCalibration<T = unknown>(
    zoneId: number,
    channelId: number,
    payload: { ml_per_sec: number; k_ms_per_ml_l?: number | null },
  ): Promise<T> {
    return apiPut<T>(`/zones/${zoneId}/pump-calibrations/${channelId}`, payload)
  },

  startRelayAutotune(zoneId: number, payload: { pid_type: string }): Promise<unknown> {
    return apiPost<unknown>(`/zones/${zoneId}/relay-autotune`, payload)
  },

  getRelayAutotuneStatus<T = unknown>(
    zoneId: number,
    params?: { pid_type?: string },
  ): Promise<T> {
    return apiGet<T>(`/zones/${zoneId}/relay-autotune/status`, { params })
  },

  attachRecipe<T = Record<string, unknown>>(
    zoneId: number,
    payload: { recipe_id: number; start_at?: string },
  ): Promise<T> {
    return apiPost<T>(`/zones/${zoneId}/attach-recipe`, payload)
  },
}
