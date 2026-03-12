import { computed, ref, watch } from 'vue'
import type { ComputedRef } from 'vue'
import { logger } from '@/utils/logger'

export const telemetryRanges = ['1H', '24H', '7D', '30D', 'ALL'] as const
export type TelemetryRange = (typeof telemetryRanges)[number]

export interface ZoneTelemetryChartDeps {
  fetchHistory: (
    zoneId: number,
    metric: 'PH' | 'EC',
    params: { from?: string; to: string }
  ) => Promise<Array<{ ts: number; value: number }>>
}

export function useZoneTelemetryChart(
  zoneId: ComputedRef<number | undefined>,
  deps: ZoneTelemetryChartDeps
) {
  const { fetchHistory } = deps
  const chartTimeRange = ref<TelemetryRange>('24H')
  const chartDataPh = ref<Array<{ ts: number; value: number }>>([])
  const chartDataEc = ref<Array<{ ts: number; value: number }>>([])
  let chartDataRequestVersion = 0

  const telemetryRangeKey = computed(() =>
    zoneId.value ? `zone:${zoneId.value}:telemetryRange` : null
  )

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

  async function refreshChartData(timeRange: TelemetryRange): Promise<void> {
    const requestVersion = ++chartDataRequestVersion
    const [phData, ecData] = await Promise.all([
      loadChartData('PH', timeRange),
      loadChartData('EC', timeRange),
    ])
    if (requestVersion !== chartDataRequestVersion) return
    chartDataPh.value = phData
    chartDataEc.value = ecData
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
    if (!newZoneId) return
    void refreshChartData(chartTimeRange.value)
  })

  return {
    chartTimeRange,
    chartDataPh,
    chartDataEc,
    onChartTimeRangeChange,
    refreshChartData,
    initStoredRange,
  }
}
