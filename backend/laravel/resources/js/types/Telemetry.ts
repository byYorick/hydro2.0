/**
 * Телеметрия зоны (последние значения)
 */
export interface ZoneTelemetry {
  ph?: number | null
  ec?: number | null
  temperature?: number | null
  humidity?: number | null
  co2?: number | null
  last_updated?: string
}

/**
 * Образец телеметрии из истории
 */
export interface TelemetrySample {
  ts: number
  value: number
  avg?: number | null
  min?: number | null
  max?: number | null
}

export const telemetryRanges = ['1H', '24H', '7D', '30D', 'ALL'] as const
export type TelemetryRange = (typeof telemetryRanges)[number]

/**
 * Тип метрики телеметрии
 */
export type TelemetryMetric = 'PH' | 'EC' | 'TEMPERATURE' | 'HUMIDITY' | 'SOIL_MOISTURE'
