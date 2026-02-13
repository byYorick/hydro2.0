import { computed, type Ref } from 'vue'
import type { EChartsOption } from 'echarts'
import type { SimulationResults } from '@/utils/simulationResultParser'

interface UseSimulationChartParams {
  theme: Ref<unknown>
  results: Ref<SimulationResults | null>
}

function resolveCssColor(variable: string, fallback: string): string {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

export function useSimulationChart(params: UseSimulationChartParams) {
  const chartPalette = computed(() => {
    params.theme.value
    return {
      text: resolveCssColor('--text-muted', '#9ca3af'),
      textStrong: resolveCssColor('--text-primary', '#e5e7eb'),
      grid: resolveCssColor('--border-muted', '#374151'),
      ph: resolveCssColor('--accent-cyan', '#3b82f6'),
      ec: resolveCssColor('--accent-green', '#10b981'),
      temp: resolveCssColor('--accent-amber', '#f59e0b'),
    }
  })

  const chartOption = computed<EChartsOption | null>(() => {
    if (!params.results.value?.points) return null

    const points = params.results.value.points
    const phData = points.map((point) => [point.t, point.ph])
    const ecData = points.map((point) => [point.t, point.ec])
    const tempData = points.map((point) => [point.t, point.temp_air])

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
      },
      legend: {
        data: ['pH', 'EC', 'Температура воздуха'],
        textStyle: { color: chartPalette.value.textStrong },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true,
      },
      xAxis: {
        type: 'value',
        name: 'Время (ч)',
        nameTextStyle: { color: chartPalette.value.text },
        axisLabel: { color: chartPalette.value.text },
        splitLine: { lineStyle: { color: chartPalette.value.grid } },
      },
      yAxis: [
        {
          type: 'value',
          name: 'pH / EC',
          nameTextStyle: { color: chartPalette.value.text },
          axisLabel: { color: chartPalette.value.text },
          splitLine: { lineStyle: { color: chartPalette.value.grid } },
        },
        {
          type: 'value',
          name: 'Температура (°C)',
          nameTextStyle: { color: chartPalette.value.text },
          axisLabel: { color: chartPalette.value.text },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: 'pH',
          type: 'line',
          data: phData,
          smooth: true,
          lineStyle: { color: chartPalette.value.ph },
          itemStyle: { color: chartPalette.value.ph },
        },
        {
          name: 'EC',
          type: 'line',
          data: ecData,
          smooth: true,
          lineStyle: { color: chartPalette.value.ec },
          itemStyle: { color: chartPalette.value.ec },
        },
        {
          name: 'Температура воздуха',
          type: 'line',
          yAxisIndex: 1,
          data: tempData,
          smooth: true,
          lineStyle: { color: chartPalette.value.temp },
          itemStyle: { color: chartPalette.value.temp },
        },
      ],
    }
  })

  return {
    chartOption,
  }
}
