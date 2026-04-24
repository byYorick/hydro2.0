import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import CausalChainPanel from '../CausalChainPanel.vue'
import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant', 'size'],
    template: '<span :data-variant="variant"><slot /></span>',
  },
}))

function buildRun(overrides: Partial<ExecutionRun> = {}): ExecutionRun {
  return {
    execution_id: 'ex-2042',
    task_id: 't-551',
    zone_id: 12,
    task_type: 'ph_correction',
    status: 'running',
    is_active: true,
    decision_outcome: 'run',
    correlation_id: 'cw-118',
    chain: [
      { step: 'SNAPSHOT', at: '2026-02-10T12:33:52Z', ref: 'ev-8821', detail: 'pH=6.4', status: 'ok' },
      { step: 'DECISION', at: '2026-02-10T12:33:55Z', ref: 'cw-118', detail: 'DOSE_ACID 2.3 ml', status: 'ok' },
      { step: 'TASK', at: '2026-02-10T12:33:56Z', ref: 'T-551', detail: 'ae_task → dosing', status: 'ok' },
      { step: 'DISPATCH', at: '2026-02-10T12:34:07Z', ref: 'cmd-9931', detail: 'history-logger → MQTT', status: 'ok' },
      { step: 'RUNNING', at: '2026-02-10T12:34:08Z', ref: 'ex-2042', detail: 'pump_acid активен', status: 'run', live: true },
    ],
    ...overrides,
  }
}

describe('CausalChainPanel.vue', () => {
  it('рендерит 5 шагов цепочки для активного run', () => {
    const wrapper = mount(CausalChainPanel, { props: { run: buildRun() } })
    const steps = wrapper.findAll('[data-testid^="scheduler-chain-step-"]')
    expect(steps).toHaveLength(5)
    expect(wrapper.find('[data-testid="scheduler-chain-step-SNAPSHOT"]').text()).toContain('pH=6.4')
    expect(wrapper.find('[data-testid="scheduler-chain-step-RUNNING"]').text()).toContain('pump_acid активен')
  })

  it('показывает FAIL-блок с error_code и кнопку "Повторить"', () => {
    const run = buildRun({
      status: 'failed',
      is_active: false,
      error_code: 'ACT_TIMEOUT',
      chain: [
        { step: 'SNAPSHOT', at: null, ref: 'ev-8819', detail: 'pH=6.5', status: 'ok' },
        { step: 'DECISION', at: null, ref: 'cw-117', detail: 'DOSE_ACID 2.1ml', status: 'ok' },
        { step: 'FAIL', at: null, ref: 'ex-2040', detail: 'ACT_TIMEOUT pump_acid', status: 'err' },
      ],
    })
    const wrapper = mount(CausalChainPanel, {
      props: { run, errorText: 'pump_acid не ответил 3000ms' },
    })
    expect(wrapper.find('[data-testid="scheduler-chain-error"]').text()).toContain('ACT_TIMEOUT')
    expect(wrapper.find('[data-testid="scheduler-chain-error"]').text()).toContain('pump_acid не ответил 3000ms')
    expect(wrapper.find('[data-testid="scheduler-chain-retry"]').exists()).toBe(true)
  })

  it('для SKIP-run показывает только 2 шага и skip-бейдж', () => {
    const run = buildRun({
      status: 'completed',
      is_active: false,
      decision_outcome: 'skip',
      chain: [
        { step: 'SNAPSHOT', at: null, ref: 'ev-8818', detail: 'EC=1.52', status: 'ok' },
        { step: 'DECISION', at: null, ref: 'cw-116', detail: 'SKIP · в пределах target', status: 'skip' },
      ],
    })
    const wrapper = mount(CausalChainPanel, { props: { run } })
    expect(wrapper.findAll('[data-testid^="scheduler-chain-step-"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="scheduler-chain-retry"]').exists()).toBe(false)
  })

  it('эмитит события close/retry/open-events', async () => {
    const run = buildRun({
      status: 'failed',
      is_active: false,
      error_code: 'ACT_TIMEOUT',
    })
    const wrapper = mount(CausalChainPanel, { props: { run } })

    await wrapper.find('[data-testid="scheduler-chain-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()

    await wrapper.find('[data-testid="scheduler-chain-retry"]').trigger('click')
    expect(wrapper.emitted('retry')?.[0]).toEqual(['ex-2042'])

    await wrapper.find('[data-testid="scheduler-chain-open-events"]').trigger('click')
    expect(wrapper.emitted('open-events')?.[0]).toEqual(['ex-2042'])
  })
})
