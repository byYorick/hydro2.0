import { describe, expect, it } from 'vitest'
import {
  formatDate,
  formatDuration,
  formatNumber,
  toComparisonRows,
  toRecipeAnalytics,
  toRecipeOptions,
  toTelemetryAggregates,
  toZoneOptions,
} from '../useAnalyticsTransforms'

describe('useAnalyticsTransforms', () => {
  it('форматирует числа, длительность и дату', () => {
    expect(formatNumber(1.234, 2)).toBe('1.23')
    expect(formatNumber(null, 2)).toBe('—')
    expect(formatDuration(12)).toBe('12.0 ч')
    expect(formatDuration(48)).toBe('2.0 дн.')
    expect(formatDate(undefined)).toBe('—')
  })

  it('преобразует payload зон и рецептов', () => {
    const zones = toZoneOptions({ data: { data: [{ id: 1, name: 'Zone A' }, { id: 2 }] } })
    expect(zones).toEqual([
      { id: 1, name: 'Zone A' },
      { id: 2, name: 'Zone #2' },
    ])

    const recipes = toRecipeOptions({ data: { data: [{ id: 10, name: 'R-1' }] } })
    expect(recipes).toEqual([{ id: 10, name: 'R-1' }])
  })

  it('преобразует payload агрегатов, аналитики и сравнения', () => {
    const aggregates = toTelemetryAggregates({ data: { data: [{ ts: '2026-01-01', avg: 1, min: 0, max: 2 }] } })
    expect(aggregates).toHaveLength(1)

    const analytics = toRecipeAnalytics({
      data: {
        data: { data: [{ id: 1 }], total: 11, per_page: 25 },
        stats: { avg_efficiency: 0.9 },
      },
    }, 10)
    expect(analytics.total).toBe(11)
    expect(analytics.perPage).toBe(25)
    expect(analytics.runs).toHaveLength(1)

    const comparison = toComparisonRows({ data: { data: [{ recipe_id: 1, runs_count: 5 }] } })
    expect(comparison).toEqual([{ recipe_id: 1, runs_count: 5 }])
  })
})
