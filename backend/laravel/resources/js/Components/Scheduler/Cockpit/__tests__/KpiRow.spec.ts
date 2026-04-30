import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KpiRow from '../KpiRow.vue'

describe('KpiRow.vue', () => {
  it('рендерит 4 KPI карточки с правильными значениями', () => {
    const wrapper = mount(KpiRow, {
      props: {
        counters: { active: 1, completed_24h: 47, failed_24h: 2 },
        executableWindowsCount: 8,
        runtime: 'ae3',
        windowTypeCount: 3,
      },
    })

    expect(wrapper.find('[data-testid="scheduler-kpi-active"]').text()).toContain('1')
    expect(wrapper.find('[data-testid="scheduler-kpi-active"]').text()).toContain('runtime=ae3')
    expect(wrapper.find('[data-testid="scheduler-kpi-completed"]').text()).toContain('47')
    expect(wrapper.find('[data-testid="scheduler-kpi-failed"]').text()).toContain('2')
    expect(wrapper.find('[data-testid="scheduler-kpi-windows"]').text()).toContain('8')
    expect(wrapper.find('[data-testid="scheduler-kpi-windows"]').text()).toContain('3 типа')
  })

  it('использует переданный slo24h, если есть', () => {
    const wrapper = mount(KpiRow, {
      props: {
        counters: { active: 0, completed_24h: 0, failed_24h: 0 },
        executableWindowsCount: 0,
        slo24h: 0.959,
      },
    })
    expect(wrapper.find('[data-testid="scheduler-kpi-completed"]').text()).toContain('95.9%')
  })

  it('считает SLO из counters, если slo24h не задан', () => {
    const wrapper = mount(KpiRow, {
      props: {
        counters: { active: 0, completed_24h: 9, failed_24h: 1 },
        executableWindowsCount: 0,
      },
    })
    expect(wrapper.find('[data-testid="scheduler-kpi-completed"]').text()).toContain('90%')
  })

  it('показывает предупреждение при доле ошибок ≥25%', () => {
    const wrapper = mount(KpiRow, {
      props: {
        counters: { active: 0, completed_24h: 3, failed_24h: 1 },
        executableWindowsCount: 0,
      },
    })
    const failedCard = wrapper.find('[data-testid="scheduler-kpi-failed"]')
    expect(failedCard.text()).toContain('высокая доля ошибок')
    expect(failedCard.text()).toContain('всего 4 за 24ч')
  })

  it('не показывает предупреждение о высокой доле при доле ошибок ниже 25%', () => {
    const wrapper = mount(KpiRow, {
      props: {
        counters: { active: 0, completed_24h: 10, failed_24h: 2 },
        executableWindowsCount: 0,
      },
    })
    expect(wrapper.find('[data-testid="scheduler-kpi-failed"]').text()).not.toContain('высокая доля ошибок')
    expect(wrapper.find('[data-testid="scheduler-kpi-failed"]').text()).toContain('всего 12 за 24ч')
  })
})
