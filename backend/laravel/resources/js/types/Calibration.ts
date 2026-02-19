import type { PumpCalibrationConfig } from './Device'

/**
 * Тип компонента насоса для калибровки
 */
export type PumpCalibrationComponent = 'npk' | 'calcium' | 'magnesium' | 'micro' | 'ph_up' | 'ph_down'

/**
 * Опция канала насоса для выбора в UI
 */
export interface PumpChannelOption {
  id: number
  label: string
  channelName: string
  priority: number
  calibration: PumpCalibrationConfig | null
}

/**
 * Payload для запуска прогона калибровки
 */
export interface PumpCalibrationRunPayload {
  node_channel_id: number
  duration_sec: number
  component: PumpCalibrationComponent
}

/**
 * Payload для сохранения результата калибровки
 */
export interface PumpCalibrationSavePayload extends PumpCalibrationRunPayload {
  actual_ml: number
  skip_run: true
  test_volume_l?: number
  ec_before_ms?: number
  ec_after_ms?: number
  temperature_c?: number
}
