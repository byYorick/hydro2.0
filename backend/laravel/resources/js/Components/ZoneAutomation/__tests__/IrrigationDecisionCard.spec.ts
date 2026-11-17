import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import IrrigationDecisionCard from '../IrrigationDecisionCard.vue'

describe('IrrigationDecisionCard', () => {
  it('explains the measured threshold without claiming water was delivered', () => {
    const wrapper = mount(IrrigationDecisionCard, { props: { decision: {
      outcome: 'run', strategy: 'smart_soil_v1', reason_code: 'smart_soil_below_min',
      details: { zone_average_pct: 35, run_below_pct: 38, samples: 6 },
    } } })
    expect(wrapper.text()).toContain('Полив разрешён')
    expect(wrapper.text()).toContain('Средняя влажность')
    expect(wrapper.text()).toContain('35%')
    expect(wrapper.text()).toContain('38%')
    expect(wrapper.text()).toContain('не подтверждает подачу воды')
  })

  it('keeps a degraded skip distinct from approval', () => {
    const wrapper = mount(IrrigationDecisionCard, { props: { decision: {
      outcome: 'skip', strategy: 'smart_soil_v1', reason_code: 'smart_soil_degraded_above_max', degraded: true,
    } } })
    expect(wrapper.text()).toContain('Полив пропущен')
    expect(wrapper.text()).toContain('Пониженная достоверность')
    expect(wrapper.text()).not.toContain('Полив разрешён')
  })

  it('marks missing observations and cached state explicitly', () => {
    const wrapper = mount(IrrigationDecisionCard, { props: {
      isStale: true, decision: { outcome: null, strategy: 'task', details: null },
    } })
    expect(wrapper.text()).toContain('Решение ещё не принято')
    expect(wrapper.text()).toContain('Состояние автоматики из кэша')
    expect(wrapper.text()).not.toContain('0%')
  })

  it('shows a nonblocking temperature warning alongside the original decision', () => {
    const wrapper = mount(IrrigationDecisionCard, { props: { decision: {
      outcome: 'run', strategy: 'task', reason_code: 'irrigation_task_strategy_run',
      details: { solution_temp: { reason_code: 'solution_temp_unavailable', blocks_irrigation: false } },
    } } })
    expect(wrapper.text()).toContain('Полив разрешён')
    expect(wrapper.text()).toContain('это предупреждение не запрещает полив')
  })
})
