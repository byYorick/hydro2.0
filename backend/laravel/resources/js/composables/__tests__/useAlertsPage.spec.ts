import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const alertsSeed = vi.hoisted(() => [
  {
    id: 1,
    type: 'AE3_TASK_FAILED',
    code: 'biz_ae3_task_failed',
    severity: 'error',
    zone: { id: 1, name: 'Zone A1' },
    zone_id: 1,
    created_at: '2025-01-01T10:00:00Z',
    status: 'active',
  },
  {
    id: 2,
    type: 'EC_LOW',
    code: 'biz_ec_low',
    severity: 'warning',
    zone: { id: 2, name: 'Zone B2' },
    zone_id: 2,
    created_at: '2025-01-01T11:00:00Z',
    status: 'resolved',
  },
  {
    id: 3,
    type: 'TEMP_HIGH',
    code: 'biz_temp_high',
    severity: 'warning',
    zone: { id: 1, name: 'Zone A1' },
    zone_id: 1,
    created_at: '2025-01-01T12:00:00Z',
    status: 'active',
  },
  {
    id: 4,
    type: 'NO_FLOW',
    code: 'biz_no_flow',
    severity: 'critical',
    zone: { id: 2, name: 'Zone B2' },
    zone_id: 2,
    created_at: '2025-01-01T09:00:00Z',
    status: 'active',
  },
])

const axiosGetMock = vi.hoisted(() => vi.fn())
const subscribeManagedChannelEventsMock = vi.hoisted(() => vi.fn(() => vi.fn()))

vi.mock('axios', () => {
  const axiosInstance = {
    get: (...args: Parameters<typeof axiosGetMock>) => axiosGetMock(...args),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  }

  return {
    default: {
      ...axiosInstance,
      create: () => axiosInstance,
    },
  }
})

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      alerts: alertsSeed,
      zones: [
        { id: 1, name: 'Zone A1' },
        { id: 2, name: 'Zone B2' },
      ],
    },
  }),
}))

vi.mock('@/ws/managedChannelEvents', () => ({
  subscribeManagedChannelEvents: (...args: Parameters<typeof subscribeManagedChannelEventsMock>) => subscribeManagedChannelEventsMock(...args),
}))

import { useAlertsPage } from '../useAlertsPage'

const Harness = defineComponent({
  setup() {
    const page = useAlertsPage()
    return page
  },
  template: '<div />',
})

describe('useAlertsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.history.replaceState({}, '', '/alerts')
    axiosGetMock.mockReset()
    axiosGetMock.mockResolvedValue({ data: { data: alertsSeed } })
    subscribeManagedChannelEventsMock.mockClear()
  })

  const mountHarness = () => mount(Harness, {
    global: {
      plugins: [createPinia()],
    },
  })

  it('считает alertSectionCounts только по видимым секциям', async () => {
    const wrapper = mountHarness()
    await wrapper.vm.$nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))

    // @ts-expect-error harness exposes composable return
    const counts = wrapper.vm.alertSectionCounts
    expect(counts).toEqual({
      automation_block: 1,
      safety: 1,
      other_active: 1,
      resolved: 0,
      activeTotal: 3,
    })
  })

  it('группирует active секции по zoneGroups и сортирует внутри секции', async () => {
    const wrapper = mountHarness()
    await wrapper.vm.$nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))

    // @ts-expect-error harness exposes composable return
    const sections = wrapper.vm.groupedAlertSections as Array<{
      key: string
      items: Array<{ id: number }>
      zoneGroups?: Array<{ testIdSuffix: string; items: Array<{ id: number }> }>
    }>

    const automation = sections.find((section) => section.key === 'automation_block')
    const safety = sections.find((section) => section.key === 'safety')
    const other = sections.find((section) => section.key === 'other_active')

    expect(automation?.zoneGroups?.map((group) => group.testIdSuffix)).toEqual(['1'])
    expect(safety?.zoneGroups?.map((group) => group.testIdSuffix)).toEqual(['2'])
    expect(other?.zoneGroups?.map((group) => group.testIdSuffix)).toEqual(['1'])
    expect(safety?.items.map((item) => item.id)).toEqual([4])
    expect(other?.items.map((item) => item.id)).toEqual([3])
    expect(sections.some((section) => section.key === 'resolved')).toBe(false)
  })

  it('включает resolved секцию и пересчитывает activeTotal при status=all', async () => {
    const wrapper = mountHarness()
    await wrapper.vm.$nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))

    // @ts-expect-error harness exposes composable return
    wrapper.vm.statusFilter = 'all'
    await wrapper.vm.$nextTick()

    // @ts-expect-error harness exposes composable return
    const sections = wrapper.vm.groupedAlertSections as Array<{ key: string; items: Array<{ id: number }> }>
    // @ts-expect-error harness exposes composable return
    const counts = wrapper.vm.alertSectionCounts

    expect(sections.some((section) => section.key === 'resolved')).toBe(true)
    expect(sections.find((section) => section.key === 'resolved')?.items.map((item) => item.id)).toEqual([2])
    expect(counts.resolved).toBe(1)
    expect(counts.activeTotal).toBe(3)
  })
})
