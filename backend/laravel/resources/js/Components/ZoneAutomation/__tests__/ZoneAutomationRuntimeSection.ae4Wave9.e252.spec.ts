import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiGetMock = vi.hoisted(() => vi.fn())
const pageProps = vi.hoisted(() => ({
  automationStateBootstrap: null as unknown,
  automationState: undefined as unknown,
}))

vi.mock('@/utils/env', () => ({
  readBooleanEnv: () => false,
}))

vi.mock('@/utils/echoClient', () => ({
  getEchoInstance: () => null,
  onWsStateChange: () => () => {},
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: pageProps,
  }),
}))

async function unwrapAutomation(rawPromise: Promise<unknown>): Promise<unknown> {
  const raw = await rawPromise
  if (raw && typeof raw === 'object' && 'data' in (raw as Record<string, unknown>)) {
    return (raw as { data: unknown }).data
  }
  return raw
}

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      getState: (zoneId: number) =>
        unwrapAutomation(apiGetMock(`/api/zones/${zoneId}/state`)),
    },
  },
}))

vi.mock('@/composables/useCorrectionPumpHoverData', () => ({
  useCorrectionPumpHoverData: () => ({ pumpHoverByChannel: { value: {} } }),
}))

import ZoneAutomationRuntimeSection from '@/Components/ZoneAutomation/ZoneAutomationRuntimeSection.vue'

function baseState(overrides: Record<string, unknown> = {}) {
  return {
    zone_id: 5,
    state: 'READY',
    state_label: 'Готов',
    state_details: {
      started_at: null,
      elapsed_sec: 0,
      progress_percent: 0,
      failed: false,
    },
    system_config: {
      tanks_count: 2,
      system_type: 'drip',
      clean_tank_capacity_l: null,
      nutrient_tank_capacity_l: null,
    },
    current_levels: {
      clean_tank_level_percent: 0,
      nutrient_tank_level_percent: 0,
      ph: null,
      ec: null,
    },
    active_processes: {
      pump_in: false,
      circulation_pump: false,
      ph_correction: false,
      ec_correction: false,
      active_doses: [],
    },
    timeline: [],
    next_state: null,
    estimated_completion_sec: null,
    ...overrides,
  }
}

const stubs = {
  AutomationStatusHeader: true,
  AutomationProcessDiagram: true,
  AutomationTimeline: true,
  AutomationRuntimeMetrics: true,
  AutomationObservabilityPanel: true,
  Badge: true,
}

describe('ZoneAutomationRuntimeSection E252 unattended', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    pageProps.automationStateBootstrap = null
    pageProps.automationState = undefined
    apiGetMock.mockReset()
  })

  it('e252 empty unattended_blockers shows can leave', async () => {
    apiGetMock.mockResolvedValue({
      data: baseState({
        unattended_ready: true,
        unattended_blockers: [],
      }),
    })

    const wrapper = mount(ZoneAutomationRuntimeSection, {
      props: { zoneId: 5 },
      global: { stubs },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="zone-unattended-status"]').text()).toBe(
      'Можно уйти на неделю',
    )
  })

  it('e252 nonempty blockers shows russian reasons', async () => {
    apiGetMock.mockResolvedValue({
      data: baseState({
        unattended_ready: false,
        unattended_blockers: [
          {
            reason_code: 'control_mode_manual',
            human_message: 'Ручной режим — уйти нельзя',
          },
        ],
      }),
    })

    const wrapper = mount(ZoneAutomationRuntimeSection, {
      props: { zoneId: 5 },
      global: { stubs },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="zone-unattended-blockers"]').text()).toContain(
      'Ручной режим — уйти нельзя',
    )
  })

  it('e252 raw reason_code is not shown to operator', async () => {
    apiGetMock.mockResolvedValue({
      data: baseState({
        unattended_ready: false,
        unattended_blockers: [
          {
            reason_code: 'control_mode_manual',
            human_message: 'Ручной режим — уйти нельзя',
          },
        ],
      }),
    })

    const wrapper = mount(ZoneAutomationRuntimeSection, {
      props: { zoneId: 5 },
      global: { stubs },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="zone-unattended-ready"]').text()).not.toContain(
      'control_mode_manual',
    )
  })
})
