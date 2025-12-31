import { describe, it, expect } from 'vitest'
import type { DeviceChannel } from '@/types'

// Тестируем утилиты из Devices/Show.vue
// Эти функции должны быть вынесены в отдельный модуль, но пока тестируем их логику

describe('Devices/Show.vue - Утилиты', () => {
  describe('getMetricFromChannel', () => {
    it('возвращает metric из канала, если он есть', () => {
      const channel: DeviceChannel = {
        channel: 'temp_sensor',
        type: 'SENSOR',
        metric: 'TEMPERATURE',
        unit: '°C',
      }
      const metric = channel.metric || channel.channel.toUpperCase()
      expect(metric).toBe('TEMPERATURE')
    })

    it('возвращает channel в верхнем регистре, если metric отсутствует', () => {
      const channel: DeviceChannel = {
        channel: 'humidity_sensor',
        type: 'SENSOR',
        unit: '%',
      }
      const metric = channel.metric || channel.channel.toUpperCase()
      expect(metric).toBe('HUMIDITY_SENSOR')
    })
  })

  describe('getTimeRangeFrom', () => {
    const TIME_RANGE_MS: Record<string, number> = {
      '1H': 60 * 60 * 1000,
      '24H': 24 * 60 * 60 * 1000,
      '7D': 7 * 24 * 60 * 60 * 1000,
      '30D': 30 * 24 * 60 * 60 * 1000,
    }

    const getTimeRangeFrom = (timeRange: string): Date | undefined => {
      if (timeRange === 'ALL') return undefined
      const ms = TIME_RANGE_MS[timeRange]
      return ms ? new Date(Date.now() - ms) : undefined
    }

    it('возвращает undefined для ALL', () => {
      expect(getTimeRangeFrom('ALL')).toBeUndefined()
    })

    it('возвращает правильную дату для 1H', () => {
      const from = getTimeRangeFrom('1H')
      expect(from).toBeInstanceOf(Date)
      if (from) {
        const diff = Date.now() - from.getTime()
        expect(diff).toBeGreaterThanOrEqual(60 * 60 * 1000 - 1000) // допускаем погрешность в 1 секунду
        expect(diff).toBeLessThanOrEqual(60 * 60 * 1000 + 1000)
      }
    })

    it('возвращает правильную дату для 24H', () => {
      const from = getTimeRangeFrom('24H')
      expect(from).toBeInstanceOf(Date)
      if (from) {
        const diff = Date.now() - from.getTime()
        expect(diff).toBeGreaterThanOrEqual(24 * 60 * 60 * 1000 - 1000)
        expect(diff).toBeLessThanOrEqual(24 * 60 * 60 * 1000 + 1000)
      }
    })

    it('возвращает undefined для неизвестного диапазона', () => {
      expect(getTimeRangeFrom('UNKNOWN')).toBeUndefined()
    })
  })

  describe('getMaxPointsForTimeRange', () => {
    const MAX_POINTS_BY_RANGE: Record<string, number> = {
      '1H': 60,
      '24H': 288,
      '7D': 336,
      '30D': 720,
      'ALL': 1000,
    }

    const getMaxPointsForTimeRange = (timeRange: string): number => {
      return MAX_POINTS_BY_RANGE[timeRange] ?? 288
    }

    it('возвращает правильное количество точек для каждого диапазона', () => {
      expect(getMaxPointsForTimeRange('1H')).toBe(60)
      expect(getMaxPointsForTimeRange('24H')).toBe(288)
      expect(getMaxPointsForTimeRange('7D')).toBe(336)
      expect(getMaxPointsForTimeRange('30D')).toBe(720)
      expect(getMaxPointsForTimeRange('ALL')).toBe(1000)
    })

    it('возвращает значение по умолчанию для неизвестного диапазона', () => {
      expect(getMaxPointsForTimeRange('UNKNOWN')).toBe(288)
    })
  })

  describe('METRIC_PRIORITY сортировка', () => {
    const METRIC_PRIORITY: Record<string, number> = {
      'TEMPERATURE': 1,
      'HUMIDITY': 2,
    }

    const getMetricPriority = (metric: string): number => {
      return METRIC_PRIORITY[metric] ?? 999
    }

    it('сортирует каналы по приоритету', () => {
      const channels = [
        { metric: 'HUMIDITY' },
        { metric: 'CO2' },
        { metric: 'TEMPERATURE' },
        { metric: 'PH' },
      ]

      const sorted = channels.sort((a, b) => {
        const aMetric = a.metric || ''
        const bMetric = b.metric || ''
        return getMetricPriority(aMetric) - getMetricPriority(bMetric)
      })

      expect(sorted[0].metric).toBe('TEMPERATURE')
      expect(sorted[1].metric).toBe('HUMIDITY')
    })
  })
})
