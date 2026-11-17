import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import SchedulerDispatchMetricsStrip from '../SchedulerDispatchMetricsStrip.vue'

vi.mock('@/composables/useSchedulerDispatchMetrics', () => ({
  useSchedulerDispatchMetrics: () => ({
    metrics: ref({
      pendingIntents: 3,
      oldestPendingAgeSec: 120,
      dispatchCycleOverrunSec: 1.5,
    }),
    loading: ref(false),
    error: ref(null),
    refreshedAt: ref('2026-06-29T10:00:00.000Z'),
  }),
}))

describe('SchedulerDispatchMetricsStrip', () => {
  it('рендерит глобальные метрики планировщика', () => {
    const wrapper = mount(SchedulerDispatchMetricsStrip)

    expect(wrapper.find('[data-testid="scheduler-dispatch-metrics-strip"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Запросов, ожидающих приёма в работу')
    expect(wrapper.text()).toContain('120 сек')
    expect(wrapper.text()).toContain('1,5 сек')
  })
})
