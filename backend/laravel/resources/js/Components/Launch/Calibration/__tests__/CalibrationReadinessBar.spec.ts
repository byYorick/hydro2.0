import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CalibrationReadinessBar from '../CalibrationReadinessBar.vue'
import type { CalibrationContract } from '@/composables/useCalibrationContracts'

const passed: CalibrationContract = {
  id: 'a',
  subsystem: 'pump',
  component: 'npk',
  title: 'A',
  status: 'passed',
  required: true,
}

const blocker: CalibrationContract = {
  id: 'b',
  subsystem: 'pump',
  component: 'ph_up',
  title: 'B',
  status: 'blocker',
  required: true,
  action: { label: 'go', target: 'pumps' },
}

describe('CalibrationReadinessBar', () => {
  it('renders progress chip', () => {
    const w = mount(CalibrationReadinessBar, {
      props: {
        contracts: [passed],
        summary: { passed: 1, total: 1, blockers: 0 },
      },
    })
    expect(w.text()).toContain('1/1')
    expect(w.text()).toContain('все обязательные контракты пройдены')
  })

  it('shows blocker count and primary "Калибровка насосов" button', () => {
    const w = mount(CalibrationReadinessBar, {
      props: {
        contracts: [passed, blocker],
        summary: { passed: 1, total: 2, blockers: 1 },
      },
    })
    expect(w.text()).toContain('1 блокер')
    const pumpBtn = w
      .findAll('button')
      .find((b) => b.text().includes('Калибровка насосов'))
    expect(pumpBtn).toBeTruthy()
  })

  it('emits open-pump-wizard', async () => {
    const w = mount(CalibrationReadinessBar, {
      props: {
        contracts: [passed],
        summary: { passed: 1, total: 1, blockers: 0 },
      },
    })
    const pumpBtn = w
      .findAll('button')
      .find((b) => b.text().includes('Калибровка насосов'))!
    await pumpBtn.trigger('click')
    expect(w.emitted('open-pump-wizard')).toBeTruthy()
  })

  it('emits open-contract for blocker chip click', async () => {
    const w = mount(CalibrationReadinessBar, {
      props: {
        contracts: [blocker],
        summary: { passed: 0, total: 1, blockers: 1 },
      },
    })
    const tag = w
      .findAll('button')
      .find((b) => b.text().includes('ph_up'))!
    await tag.trigger('click')
    const events = w.emitted('open-contract')
    expect(events).toBeTruthy()
    expect((events![0][0] as CalibrationContract).id).toBe('b')
  })
})
