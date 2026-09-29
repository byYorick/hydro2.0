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

describe('ZoneAutomationRuntimeSection AE4 wave2', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiGetMock.mockReset()
    pageProps.automationStateBootstrap = null
    pageProps.automationState = undefined
  })

  it('shows pause text without failed mark', async () => {
    apiGetMock.mockResolvedValue({
      data: baseState({
        planting_decision: {
          reason_code: 'night_skip',
          human_message: 'Ночь: полив пропущен',
          failed: false,
        },
      }),
    })

    const wrapper = mount(ZoneAutomationRuntimeSection, {
      props: { zoneId: 5 },
      global: {
        stubs: {
          AutomationStatusHeader: true,
          AutomationProcessDiagram: true,
          AutomationTimeline: true,
          AutomationRuntimeMetrics: true,
          AutomationObservabilityPanel: true,
          Badge: true,
        },
      },
    })
    await flushPromises()

    const decision = wrapper.get('[data-testid="zone-planting-decision"]')
    expect({
      pauseText: decision.text(),
      looksLikeAccident: wrapper.text().includes('Сбой автоматики'),
    }).toEqual({
      pauseText: expect.stringContaining('Ночь: полив пропущен'),
      looksLikeAccident: false,
    })
  })

  it('shows failure when state_details.failed is true', async () => {
    apiGetMock.mockResolvedValue({
      data: baseState({
        state_details: {
          started_at: null,
          elapsed_sec: 0,
          progress_percent: 0,
          failed: true,
          error_code: 'ae4_command_not_done',
          human_error_message:
            'Команда ae4-t1-z1-s1 завершилась статусом ERROR, ожидался DONE',
        },
      }),
    })

    const wrapper = mount(ZoneAutomationRuntimeSection, {
      props: { zoneId: 5 },
      global: {
        stubs: {
          AutomationStatusHeader: true,
          AutomationProcessDiagram: true,
          AutomationTimeline: true,
          AutomationRuntimeMetrics: true,
          AutomationObservabilityPanel: true,
          Badge: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Сбой автоматики')
  })
})
