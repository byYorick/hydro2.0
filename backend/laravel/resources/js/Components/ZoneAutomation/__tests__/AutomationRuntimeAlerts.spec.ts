import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AutomationRuntimeAlerts from '../AutomationRuntimeAlerts.vue'

describe('AutomationRuntimeAlerts', () => {
  it('показывает исторический сбой с пояснением после ack', () => {
    const wrapper = mount(AutomationRuntimeAlerts, {
      props: {
        failed: true,
        activeFailure: false,
        historicalFailure: true,
        humanErrorMessage: 'Состояние IRR-ноды не совпало с ожиданиями автоматики.',
        errorCode: 'irr_state_mismatch',
      },
    })

    expect(wrapper.text()).toContain('Последний сбой автоматики')
    expect(wrapper.text()).toContain('irr_state_mismatch')
    expect(wrapper.text()).toContain('Активный алерт подтверждён')
  })

  it('показывает активный сбой', () => {
    const wrapper = mount(AutomationRuntimeAlerts, {
      props: {
        failed: true,
        activeFailure: true,
        historicalFailure: false,
        humanErrorMessage: 'Таймаут команды',
        errorCode: 'command_timeout',
      },
    })

    expect(wrapper.text()).toContain('Сбой автоматики')
    expect(wrapper.text()).not.toContain('Активный алерт подтверждён')
  })
})
