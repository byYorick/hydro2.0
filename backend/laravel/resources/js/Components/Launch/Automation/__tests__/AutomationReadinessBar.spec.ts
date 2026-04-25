import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AutomationReadinessBar from '../AutomationReadinessBar.vue'
import type { AutomationContract } from '@/composables/useAutomationContracts'

const passed: AutomationContract = {
  id: 'a',
  subsystem: 'bindings',
  component: 'irrigation',
  title: 'A',
  status: 'passed',
  required: true,
}

const blocker: AutomationContract = {
  id: 'b',
  subsystem: 'bindings',
  component: 'ph_correction',
  title: 'B',
  status: 'blocker',
  required: true,
  action: { label: 'go', target: 'bindings' },
}

describe('AutomationReadinessBar', () => {
  it('renders progress chip with passed/total', () => {
    const w = mount(AutomationReadinessBar, {
      props: {
        contracts: [passed],
        summary: { passed: 1, total: 1, blockers: 0 },
      },
    })
    expect(w.text()).toContain('1/1')
    expect(w.text()).toContain('все обязательные контракты пройдены')
  })

  it('shows blocker count when summary.blockers > 0', () => {
    const w = mount(AutomationReadinessBar, {
      props: {
        contracts: [passed, blocker],
        summary: { passed: 1, total: 2, blockers: 1 },
      },
    })
    expect(w.text()).toContain('1 блокер')
  })

  it('renders one button per blocker contract and emits open-contract', async () => {
    const w = mount(AutomationReadinessBar, {
      props: {
        contracts: [passed, blocker],
        summary: { passed: 1, total: 2, blockers: 1 },
      },
    })
    const blockerBtns = w
      .findAll('button')
      .filter((b) => b.text().includes('ph_correction'))
    expect(blockerBtns.length).toBe(1)
    await blockerBtns[0].trigger('click')
    const events = w.emitted('open-contract')
    expect(events).toBeTruthy()
    expect((events![0][0] as AutomationContract).id).toBe('b')
  })

  it('renders one segment per contract', () => {
    const w = mount(AutomationReadinessBar, {
      props: {
        contracts: [passed, blocker, { ...passed, id: 'c', status: 'optional' }],
        summary: { passed: 1, total: 2, blockers: 1 },
      },
    })
    // 3 contracts → 3 colored segments (sibling spans inside the bar)
    const segments = w.findAll('span.flex-1')
    expect(segments.length).toBe(3)
  })
})
