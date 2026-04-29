import { computed, ref, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { logger } from '@/utils/logger'
import { telemetryRanges, type TelemetryRange } from '@/types'

export interface ZoneTelemetryChartDeps {
  fetchHistory: (
    zoneId: number,
    metric: 'PH' | 'EC',
    params: { from?: string; to: string }
  ) => Promise<Array<{ ts: number; value: number }>>
  fetchHistoryWithNodes: (
    zoneId: number,
    metric: 'SOIL_MOISTURE',
    params: { from?: string; to: string }
  ) => Promise<Record<number, Array<{ ts: number; value: number }>>>
  hasSoilMoisture: Ref<boolean>
}

export function useZoneTelemetryChart(
  zoneId: ComputedRef<number | undefined>,
  deps: ZoneTelemetryChartDeps
) {
  const { fetchHistory, fetchHistoryWithNodes, hasSoilMoisture } = deps
  const chartTimeRange = ref<TelemetryRange>('24H')
  const isChartLoading = ref(false)
  const chartDataPh = ref<Array<{ ts: number; value: number }>>([])
  const chartDataEc = ref<Array<{ ts: number; value: number }>>([])
  const chartDataSoilMoisture = ref<Record<number, Array<{ ts: number; value: number }>>>({})
  let chartDataRequestVersion = 0

  const telemetryRangeKey = computed(() =>
    zoneId.value ? `zone:${zoneId.value}:telemetryRange` : null
  )

  const normalizeRealtimeTimestamp = (ts: number): number => {
    return ts < 10_000_000_000 ? ts * 1000 : ts
  }

  const metricWindowMsByRange: Partial<Record<TelemetryRange, number>> = {
    '1H': 60 * 60 * 1000,
    '24H': 24 * 60 * 60 * 1000,
    '7D': 7 * 24 * 60 * 60 * 1000,
    '30D': 30 * 24 * 60 * 60 * 1000,
  }

  const pruneSeries = (series: Array<{ ts: number; value: number }>): void => {
    if (chartTimeRange.value === 'ALL') {
      const overflow = series.length - 1000
      if (overflow > 0) {
        series.splice(0, overflow)
      }
      return
    }

    const windowMs = metricWindowMsByRange[chartTimeRange.value]
    if (!windowMs) {
      return
    }

    const cutoffTs = Date.now() - windowMs
    let firstVisibleIndex = 0
    while (firstVisibleIndex < series.length && series[firstVisibleIndex].ts < cutoffTs) {
      firstVisibleIndex += 1
    }

    if (firstVisibleIndex > 0) {
      series.splice(0, firstVisibleIndex)
    }
  }

  const appendPointToSeries = (
    series: Array<{ ts: number; value: number }>,
    point: { ts: number; value: number }
  ): void => {
    const normalizedPoint = {
      ts: normalizeRealtimeTimestamp(point.ts),
      value: point.value,
    }

    const lastPoint = series[series.length - 1]
    if (
      lastPoint &&
      lastPoint.ts === normalizedPoint.ts &&
      lastPoint.value === normalizedPoint.value
    ) {
      return
    }

    if (lastPoint && normalizedPoint.ts < lastPoint.ts) {
      return
    }

    series.push(normalizedPoint)
    pruneSeries(series)
  }

  const appendRealtimePoint = (metricType: string, point: { ts: number; value: number }): void => {
    const normalizedMetric = String(metricType).trim().toUpperCase()

    if (normalizedMetric === 'PH') {
      appendPointToSeries(chartDataPh.value, point)
      return
    }

    if (normalizedMetric === 'EC') {
      appendPointToSeries(chartDataEc.value, point)
    }
  }

  function getStoredTelemetryRange(): TelemetryRange | null {
    if (typeof window === 'undefined') return null
    const key = telemetryRangeKey.value
    if (!key) return null
    const stored = window.localStorage.getItem(key)
    return telemetryRanges.includes(stored as TelemetryRange) ? (stored as TelemetryRange) : null
  }

  async function loadChartData(
    metric: 'PH' | 'EC',
    timeRange: TelemetryRange
  ): Promise<Array<{ ts: number; value: number }>> {
    const requestZoneId = zoneId.value
    if (!requestZoneId) return []

    const now = new Date()
    let from: Date | null = null
    switch (timeRange) {
      case '1H': from = new Date(now.getTime() - 60 * 60 * 1000); break
      case '24H': from = new Date(now.getTime() - 24 * 60 * 60 * 1000); break
      case '7D': from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000); break
      case '30D': from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000); break
      case 'ALL': from = null; break
    }

    try {
      const params: { from?: string; to: string } = { to: now.toISOString() }
      if (from) params.from = from.toISOString()
      return await fetchHistory(requestZoneId, metric, params)
    } catch (err) {
      logger.error(`Failed to load ${metric} history:`, err)
      return []
    }
  }

  async function loadSoilMoistureData(
    timeRange: TelemetryRange
  ): Promise<Record<number, Array<{ ts: number; value: number }>>> {
    const requestZoneId = zoneId.value
    if (!requestZoneId) return {}

    const now = new Date()
    let from: Date | null = null
    switch (timeRange) {
      case '1H': from = new Date(now.getTime() - 60 * 60 * 1000); break
      case '24H': from = new Date(now.getTime() - 24 * 60 * 60 * 1000); break
      case '7D': from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000); break
      case '30D': from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000); break
      case 'ALL': from = null; break
    }

    try {
      const params: { from?: string; to: string } = { to: now.toISOString() }
      if (from) params.from = from.toISOString()
      return await fetchHistoryWithNodes(requestZoneId, 'SOIL_MOISTURE', params)
    } catch (err) {
      logger.error('Failed to load SOIL_MOISTURE history:', err)
      return {}
    }
  }

  async function refreshChartData(timeRange: TelemetryRange): Promise<void> {
    const requestVersion = ++chartDataRequestVersion
    isChartLoading.value = true
    const soilPromise = hasSoilMoisture.value
      ? loadSoilMoistureData(timeRange)
      : Promise.resolve<Record<number, Array<{ ts: number; value: number }>>>({})

    try {
      const [phData, ecData, soilData] = await Promise.all([
        loadChartData('PH', timeRange),
        loadChartData('EC', timeRange),
        soilPromise,
      ])
      if (requestVersion !== chartDataRequestVersion) return
      chartDataPh.value = phData
      chartDataEc.value = ecData
      chartDataSoilMoisture.value = soilData
    } finally {
      if (requestVersion === chartDataRequestVersion) {
        isChartLoading.value = false
      }
    }
  }

  async function onChartTimeRangeChange(newRange: TelemetryRange): Promise<void> {
    if (chartTimeRange.value === newRange) return
    chartTimeRange.value = newRange
    await refreshChartData(newRange)
  }

  function initStoredRange(): void {
    const storedRange = getStoredTelemetryRange()
    if (storedRange) chartTimeRange.value = storedRange
  }

  watch(chartTimeRange, (value) => {
    if (typeof window === 'undefined') return
    const key = telemetryRangeKey.value
    if (!key) return
    window.localStorage.setItem(key, value)
  })

  watch(zoneId, (newZoneId, previousZoneId) => {
    if (newZoneId === previousZoneId) return
    chartDataRequestVersion += 1
    chartDataPh.value = []
    chartDataEc.value = []
    chartDataSoilMoisture.value = {}
    if (!newZoneId) return
    void refreshChartData(chartTimeRange.value)
  })

  return {
    chartTimeRange,
    chartDataPh,
    chartDataEc,
    chartDataSoilMoisture,
    isChartLoading,
    onChartTimeRangeChange,
    refreshChartData,
    initStoredRange,
    appendRealtimePoint,
  }
}
