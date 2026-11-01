import { describe, expect, it } from 'vitest'
import { mergeChartOption, readChartPalette, readCssVar } from '@/theme/chartTheme'

describe('chartTheme', () => {
  it('возвращает fallback, если CSS-переменной нет', () => {
    expect(readCssVar('--definitely-missing-token', '#fff')).toBe('#fff')
  })

  it('читает CSS-переменную с документа', () => {
    document.documentElement.style.setProperty('--status-ok', '#11aa55')
    expect(readCssVar('--status-ok', '#000')).toBe('#11aa55')
    document.documentElement.style.removeProperty('--status-ok')
  })

  it('отдаёт семантические цвета и шрифты графиков', () => {
    const palette = readChartPalette()
    expect(palette.statusOk).toBeTruthy()
    expect(palette.statusCritical).toBeTruthy()
    expect(palette.statusOffline).toBeTruthy()
    expect(palette.series.orange).toBeTruthy()
    expect(palette.series.violet).toBeTruthy()
    expect(palette.series.primary).toBeTruthy()
    expect(palette.series.lime).toBeTruthy()
    expect(palette.fontFamily).toContain('IBM Plex Sans')
    expect(palette.fontMono).toContain('JetBrains Mono')
  })

  it('сливает tooltip, не затирая formatter и размер шрифта серии', () => {
    const formatter = (): string => 'value'
    const option = mergeChartOption({
      tooltip: { formatter, textStyle: { fontSize: 14 } },
      series: [{ type: 'line', data: [1] }],
    })
    const tooltip = option.tooltip as {
      formatter: () => string
      textStyle: { fontFamily: string; fontSize: number }
    }

    expect(tooltip.formatter).toBe(formatter)
    expect(tooltip.textStyle.fontSize).toBe(14)
    expect(tooltip.textStyle.fontFamily).toContain('IBM Plex Sans')
    expect(option.backgroundColor).toBe('transparent')
  })
})
