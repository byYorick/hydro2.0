/**
 * Zones domain API client.
 *
 * Все HTTP-запросы к `/api/zones/*` ДОЛЖНЫ идти через этот модуль.
 * Composables/stores импортируют `api.zones`, а не `apiClient` напрямую.
 */
import type { Zone } from '@/types'
import type { PumpCalibrationRunPayload, PumpCalibrationSavePayload } from '@/types/Calibration'
import { apiGet, apiPost, apiPostVoid, apiPut } from './_client'

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
  list(params?: ZonesListParams): Promise<Zone[]> {
    return apiGet<Zone[]>('/zones', { params })
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
  sensorCalibrationStatus(zoneId: number): Promise<unknown> {
    return apiGet<unknown>(`/zones/${zoneId}/sensor-calibrations/status`)
  },

  sensorCalibrationsList(zoneId: number, params?: Record<string, unknown>): Promise<unknown> {
    return apiGet<unknown>(`/zones/${zoneId}/sensor-calibrations`, { params })
  },

  sensorCalibration(zoneId: number, calibrationId: number): Promise<unknown> {
    return apiGet<unknown>(`/zones/${zoneId}/sensor-calibrations/${calibrationId}`)
  },

  sensorCalibrationStart(zoneId: number, payload: Record<string, unknown>): Promise<unknown> {
    return apiPost<unknown>(`/zones/${zoneId}/sensor-calibrations`, payload)
  },

  sensorCalibrationAddPoint(
    zoneId: number,
    calibrationId: number,
    payload: Record<string, unknown>,
  ): Promise<unknown> {
    return apiPost<unknown>(
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
}
