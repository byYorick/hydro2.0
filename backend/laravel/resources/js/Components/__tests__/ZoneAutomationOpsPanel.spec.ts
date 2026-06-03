import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ZoneAutomationOpsPanel from '@/Components/ZoneAutomationOpsPanel.vue'

const baseProps = {
  canOperateAutomation: true,
  userRole: 'agronomist',
  quickActions: {
    irrigation: false,
    lighting: false,
    ph: false,
    ec: false,
  },
  automationControlMode: 'semi' as const,
  controlModeAvailable: ['auto', 'semi', 'manual'] as const,
  allowedManualSteps: [] as const,
  automationControlModeLoading: false,
  automationControlModeSaving: false,
  manualStepLoading: {
    clean_fill_start: false,
    clean_fill_stop: false,
    solution_fill_start: false,
    force_solution_fill_start: false,
    solution_fill_stop: false,
    prepare_recirculation_start: false,
    prepare_recirculation_stop: false,
    irrigation_stop: false,
    irrigation_recovery_start: false,
    irrigation_recovery_stop: false,
  },
  pendingControlModeValue: null,
  automationStateMetaLabel: null,
}

describe('ZoneAutomationOpsPanel', () => {
  it('показывает русские подписи режимов', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, { props: baseProps })
    expect(wrapper.text()).toContain('Полуавто')
    expect(wrapper.text()).toContain('Авто')
    expect(wrapper.text()).toContain('Ручной')
  })

  it('блокирует operator переход manual → auto', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, {
      props: {
        ...baseProps,
        userRole: 'operator',
        automationControlMode: 'manual',
      },
    })
    const autoButton = wrapper.findAll('button').find((btn) => btn.text().includes('Авто'))
    expect(autoButton).toBeDefined()
    expect(autoButton?.attributes('disabled')).toBeDefined()
    expect(autoButton?.attributes('title')).toContain('Оператор')
  })

  it('разрешает operator переход semi → manual', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, {
      props: {
        ...baseProps,
        userRole: 'operator',
        automationControlMode: 'semi',
      },
    })
    const manualButton = wrapper.findAll('button').find((btn) => btn.text().includes('Ручной'))
    expect(manualButton).toBeDefined()
    expect(manualButton?.attributes('disabled')).toBeUndefined()
  })
})
