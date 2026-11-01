import { computed, type Ref } from 'vue'
import { readChartPalette, readCssVar, type HydroChartPalette } from '@/theme/chartTheme'

export type ChartPalette = HydroChartPalette

export function useChartColors(theme: Ref<unknown>) {
  const palette = computed<ChartPalette>(() => {
    theme.value
    return readChartPalette()
  })

  return { palette, resolveCssColor: readCssVar }
}
