import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import TelemetryAggregatesChart from '../TelemetryAggregatesChart.vue'

vi.mock('@/Components/ChartBase.vue', () => ({
  default: { name: 'ChartBase', props: ['option'], template: '<div class="chart-base"></div>' },
}))

vi.mock('@/Components/EmptyState.vue', () => ({
  default: { name: 'EmptyState', props: ['title', 'description'], template: '<div class="empty-state"></div>' },
}))

vi.mock('@/Components/SkeletonBlock.vue', () => ({
  default: { name: 'SkeletonBlock', props: ['lines', 'lineHeight'], template: '<div class="skeleton-block"></div>' },
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({ theme: ref('light') }),
}))

describe('TelemetryAggregatesChart.vue', () => {
  it('renders chart when data is present', () => {
    const wrapper = mount(TelemetryAggregatesChart, {
      props: {
        data: [{ ts: new Date().toISOString(), avg: 6.1, min: 5.9, max: 6.3 }],
        metric: 'PH',
        period: '24ч',
        testId: 'analytics-telemetry-chart',
      },
    })

    expect(wrapper.find('[data-testid="analytics-telemetry-chart"]').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'ChartBase' }).exists()).toBe(true)
  })

  it('shows empty state when data is empty', () => {
    const wrapper = mount(TelemetryAggregatesChart, {
      props: {
        data: [],
      },
    })

    expect(wrapper.findComponent({ name: 'EmptyState' }).exists()).toBe(true)
  })

  it('shows loading state', () => {
    const wrapper = mount(TelemetryAggregatesChart, {
      props: {
        data: [],
        loading: true,
      },
    })

    expect(wrapper.findComponent({ name: 'SkeletonBlock' }).exists()).toBe(true)
  })

  it('shows error text', () => {
    const wrapper = mount(TelemetryAggregatesChart, {
      props: {
        data: [],
        error: 'Ошибка',
      },
    })

    expect(wrapper.text()).toContain('Ошибка')
  })
})
