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
}
