import { computed } from 'vue'
import { describe, expect, it } from 'vitest'
import { useCycleCenterView, type ZoneSummary } from '../useCycleCenterView'

const baseZone = (overrides: Partial<ZoneSummary>): ZoneSummary => ({
  id: 1,
  name: 'Zone A',
  status: 'RUNNING',
  greenhouse: { id: 1, name: 'GH-1' },
  telemetry: {
    ph: 5.9,
    ec: 1.8,
    temperature: 22.5,
    humidity: 55,
    co2: 650,
    updated_at: '2026-01-01T10:00:00Z',
  },
  alerts_count: 0,
  alerts_preview: [],
  devices: { total: 2, online: 2 },
  recipe: { id: 11, name: 'Recipe A' },
  plant: { id: 21, name: 'Basil' },
  cycle: { id: 31, status: 'RUNNING' },
  ...overrides,
})

describe('useCycleCenterView', () => {
  it('фильтрует зоны по строке поиска и статусу', () => {
    const zones = computed(() => [
      baseZone({ id: 1, name: 'Zone Basil', status: 'RUNNING' }),
      baseZone({
        id: 2,
        name: 'Zone Tomato',
        status: 'PAUSED',
        cycle: { id: 32, status: 'PAUSED' },
        plant: { id: 22, name: 'Tomato' },
      }),
    ])

    const view = useCycleCenterView({ zones })
    view.query.value = 'tom'
    view.statusFilter.value = 'PAUSED'

    expect(view.filteredZones.value).toHaveLength(1)
    expect(view.filteredZones.value[0].id).toBe(2)
  })

  it('переключает compact view и корректно форматирует метрики', () => {
    const zones = computed(() => [baseZone({})])
    const view = useCycleCenterView({ zones })

    expect(view.perPage.value).toBe(8)
    view.toggleDense()
    expect(view.denseView.value).toBe(true)
    expect(view.perPage.value).toBe(12)

    expect(view.formatMetric(6.123, 2)).toBe('6.12')
    expect(view.formatMetric(null, 2)).toBe('—')
    expect(view.getZoneStatusVariant('ALARM')).toBe('danger')
  })
})
