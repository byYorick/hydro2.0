import { defineComponent, h, nextTick, reactive } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useAutomationPanel } from '../useAutomationPanel'

const pageProps = reactive({
  automationStateBootstrap: null as unknown,
  automationState: undefined as unknown,
})

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: pageProps,
  }),
}))

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      getState: vi.fn(),
    },
  },
}))

vi.mock('@/stores/zones', () => ({
  useZonesStore: () => ({
    zoneEventSeq: {},
  }),
}))

vi.mock('@/ws/managedChannelEvents', () => ({
  subscribeManagedChannelEvents: vi.fn(() => () => {}),
}))

vi.mock('@/utils/echoClient', () => ({
  getConnectionState: () => ({ state: 'unavailable' }),
  onWsStateChange: () => () => {},
}))

function mountPanelHarness(zoneId = 42) {
  return mount(
    defineComponent({
      setup() {
        const panel = useAutomationPanel(
          { zoneId, fallbackTanksCount: 2, fallbackSystemType: 'drip' },
          ((event: string) => {
            void event
          }) as (e: 'state-change', state: string) => void,
        )
        return () => h('div', { 'data-testid': 'panel' }, panel.stateCode.value)
      },
    }),
  )
}

describe('useAutomationPanel hydration', () => {
  beforeEach(() => {
    pageProps.automationStateBootstrap = null
    pageProps.automationState = undefined
    vi.clearAllMocks()
  })

  it('hydrates from automationStateBootstrap without showing IDLE first', async () => {
    pageProps.automationStateBootstrap = {
      zone_id: 42,
      state: 'TANK_FILLING',
      state_label: 'Наполнение баков',
      state_details: { elapsed_sec: 5, progress_percent: 10, failed: false },
      system_config: { tanks_count: 2, system_type: 'drip' },
      current_levels: {},
      active_processes: {},
      timeline: [],
    }

    const wrapper = mountPanelHarness()
    await nextTick()

    expect(wrapper.text()).toContain('TANK_FILLING')
  })

  it('applies deferred automationState when it arrives', async () => {
    const { api } = await import('@/services/api')
    vi.mocked(api.zones.getState).mockImplementation(() => new Promise(() => {}))

    const wrapper = mountPanelHarness()
    await nextTick()
    expect(wrapper.text()).toContain('IDLE')

    pageProps.automationState = {
      zone_id: 42,
      state: 'IRRIGATING',
      state_label: 'Полив',
      state_details: { elapsed_sec: 20, progress_percent: 55, failed: false },
      system_config: { tanks_count: 2, system_type: 'drip' },
      current_levels: {},
      active_processes: {},
      timeline: [],
    }

    await nextTick()
    expect(wrapper.text()).toContain('IRRIGATING')
  })

  it('fetches from API when no page props are available', async () => {
    const { api } = await import('@/services/api')
    vi.mocked(api.zones.getState).mockResolvedValue({
      zone_id: 42,
      state: 'READY',
      state_label: 'Готов',
      state_details: { elapsed_sec: 0, progress_percent: 0, failed: false },
      system_config: { tanks_count: 2, system_type: 'drip' },
      current_levels: {},
      active_processes: {},
      timeline: [],
    })

    const wrapper = mountPanelHarness()
    await flushPromises()

    expect(api.zones.getState).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('READY')
  })
})
