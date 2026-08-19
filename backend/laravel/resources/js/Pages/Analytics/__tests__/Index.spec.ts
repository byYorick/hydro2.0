import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pageState = vi.hoisted(() => ({
  role: 'agronomist' as string,
}))

const zonesListMock = vi.hoisted(() => vi.fn())
const recipesListMock = vi.hoisted(() => vi.fn())

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/TelemetryAggregatesChart.vue', () => ({
  default: { name: 'TelemetryAggregatesChart', template: '<div data-testid="analytics-telemetry-chart" />' },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}))

vi.mock('@/services/api', () => ({
  api: {
    zones: { list: zonesListMock },
    recipes: {
      list: recipesListMock,
      analytics: vi.fn(),
      comparison: vi.fn(),
    },
    telemetry: { aggregates: vi.fn() },
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      auth: {
        user: { role: pageState.role },
      },
    },
  }),
}))

import AnalyticsIndex from '../Index.vue'

function mountAnalytics(role: string) {
  pageState.role = role
  return mount(AnalyticsIndex)
}

describe('Analytics/Index.vue', () => {
  beforeEach(() => {
    pageState.role = 'agronomist'
    zonesListMock.mockReset().mockResolvedValue([])
    recipesListMock.mockReset().mockResolvedValue([])
  })

  it('подписывает фильтр медианы как «Медиана»', async () => {
    const wrapper = mountAnalytics('operator')
    await flushPromises()

    expect(wrapper.get('[data-testid="analytics-filter-median"]').text()).toBe('Медиана')
    expect(wrapper.text()).not.toContain('Median')
  })

  it('для агронома ставит блок рецептов выше агрегатов телеметрии', async () => {
    const wrapper = mountAnalytics('agronomist')
    await flushPromises()

    const recipes = wrapper.get('[data-testid="analytics-recipes-block"]')
    const telemetry = wrapper.get('[data-testid="analytics-telemetry-block"]')
    const following = Node.DOCUMENT_POSITION_FOLLOWING

    expect(recipes.element.compareDocumentPosition(telemetry.element) & following).toBeTruthy()
    expect(wrapper.text().indexOf('Эффективность рецептов'))
      .toBeLessThan(wrapper.text().indexOf('Агрегаты телеметрии'))
  })

  it('для оператора оставляет агрегаты телеметрии выше рецептов', async () => {
    const wrapper = mountAnalytics('operator')
    await flushPromises()

    const recipes = wrapper.get('[data-testid="analytics-recipes-block"]')
    const telemetry = wrapper.get('[data-testid="analytics-telemetry-block"]')
    const following = Node.DOCUMENT_POSITION_FOLLOWING

    expect(telemetry.element.compareDocumentPosition(recipes.element) & following).toBeTruthy()
    expect(wrapper.text().indexOf('Агрегаты телеметрии'))
      .toBeLessThan(wrapper.text().indexOf('Эффективность рецептов'))
  })
})
