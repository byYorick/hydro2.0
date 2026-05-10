/** Терминальное событие UI-сессии калибровки (для обновления списков, не путать с HTTP completed). */
export type SensorCalibrationSessionOutcome = 'success' | 'failed' | 'cancelled'

/** UID канала в NodeConfig / MQTT, с которым прошивка ожидает `calibrate` (см. NODE_CHANNELS_REFERENCE). */
export type SensorCalibrationFirmwareChannelUid = 'ph_sensor' | 'ec_sensor'

/**
 * Коды доменных ошибок в теле 422 (`error_code`), когда `status === 'error'`.
 * Совпадают с бэкендом `SensorCalibrationController::mapSensorCalibrationErrorCode`.
 */
export type SensorCalibrationApiErrorCode =
  | 'sensor_calibration_channel_contract'
  | 'sensor_calibration_active_session'
  | 'ec_reference_likely_ms_cm'
  | 'ec_reference_range'
  | 'ph_reference_range'

export type SensorCalibrationStatus =
  | 'started'
  | 'point_1_pending'
  | 'point_1_done'
  | 'point_2_pending'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface SensorCalibration {
  id: number
  zone_id: number
  node_channel_id: number
  sensor_type: 'ph' | 'ec'
  status: SensorCalibrationStatus
  point_1_reference: number | null
  point_1_command_id: string | null
  point_1_sent_at: string | null
  point_1_result: string | null
  point_1_error: string | null
  point_2_reference: number | null
  point_2_command_id: string | null
  point_2_sent_at: string | null
  point_2_result: string | null
  point_2_error: string | null
  completed_at: string | null
  calibrated_by: number | null
  calibrated_by_name?: string | null
  notes: string | null
  meta: Record<string, unknown>
  node_channel?: {
    id: number
    channel: string
    node_uid?: string | null
  } | null
  created_at: string
  updated_at: string
}

export interface SensorCalibrationOverview {
  node_channel_id: number
  channel_uid: string
  sensor_type: 'ph' | 'ec'
  node_uid?: string | null
  last_calibrated_at: string | null
  days_since_calibration: number | null
  calibration_status: 'ok' | 'warning' | 'critical' | 'never'
  has_active_session: boolean
  active_calibration_id: number | null
  /** Совпадает ли `channel_uid` с ожидаемым UID прошивки для данного `sensor_type`. */
  calibration_channel_contract_ok: boolean
  /** Ожидаемый канонический UID (`ph_sensor` / `ec_sensor`). */
  calibration_channel_expected: SensorCalibrationFirmwareChannelUid
}

/** Ответ `POST .../sensor-calibrations` после успешного старта сессии. */
export interface SensorCalibrationStartResult {
  calibration: SensorCalibration
  defaults: { point_1_value: number; point_2_value: number }
}
