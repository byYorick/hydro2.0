import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ZoneAutomationOpsPanel from '@/Components/ZoneAutomationOpsPanel.vue'

describe('ZoneAutomationOpsPanel E253', () => {
  it('e253 не эмитит start-irrigation и не обещает кнопки старого ingress', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, {
      props: {
        automationControlMode: 'auto',
        automationControlModeLoading: false,
        automationControlModeSaving: false,
        pendingControlModeValue: null,
        controlModeAvailable: ['auto', 'semi', 'manual'],
        controlModeLabels: { auto: 'Авто', semi: 'Полуавто', manual: 'Ручной' },
        canOperateAutomation: true,
        canSelectMode: () => true,
        modeDisabledTitle: () => '',
        userRole: 'operator',
        allowedManualSteps: [],
        manualStepLoading: {},
        irrigationActionLoading: false,
        diagnosticsActionLoading: false,
        solutionChangeActionLoading: false,
        automationStateMetaLabel: '',
      },
      global: {
        stubs: { Badge: true, Button: true },
      },
    })

    expect(wrapper.text()).not.toContain('Запустить полив')
    expect(wrapper.text()).not.toContain('Подмена раствора')
    expect(wrapper.emitted('start-irrigation')).toBeUndefined()
    expect(wrapper.html()).not.toMatch(/start-irrigation/)
  })
})
