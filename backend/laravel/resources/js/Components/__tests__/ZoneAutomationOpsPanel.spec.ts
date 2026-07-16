import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ZoneAutomationOpsPanel from '@/Components/ZoneAutomationOpsPanel.vue'

const baseProps = {
  canOperateAutomation: true,
  userRole: 'agronomist',
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
    prepare_recirculation_stop: false,
    irrigation_stop: false,
    irrigation_recovery_stop: false,
    solution_drain_confirm: false,
    solution_refill_confirm: false,
    solution_change_abort: false,
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

  it('эмитит start-irrigation и force-irrigation для операционных кнопок полива', async () => {
    const wrapper = mount(ZoneAutomationOpsPanel, { props: baseProps })

    const startButton = wrapper.findAll('button').find((btn) => btn.text() === 'Запустить полив')
    const forceButton = wrapper.findAll('button').find((btn) => btn.text() === 'Принудительный полив')
    expect(startButton).toBeDefined()
    expect(forceButton).toBeDefined()

    await startButton!.trigger('click')
    await forceButton!.trigger('click')

    expect(wrapper.emitted('start-irrigation')).toHaveLength(1)
    expect(wrapper.emitted('force-irrigation')).toHaveLength(1)
  })

  it('блокирует кнопки полива во время выполнения команды', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, {
      props: { ...baseProps, irrigationActionLoading: true },
    })

    const irrigationButtons = wrapper
      .findAll('button')
      .filter((btn) => btn.text() === 'Отправка...')
    expect(irrigationButtons.length).toBeGreaterThanOrEqual(2)
    irrigationButtons.forEach((btn) => {
      expect(btn.attributes('disabled')).toBeDefined()
    })
  })

  it('эмитит run-diagnostics для кнопки диагностики', async () => {
    const wrapper = mount(ZoneAutomationOpsPanel, { props: baseProps })

    const diagnosticsButton = wrapper.findAll('button').find((btn) => btn.text() === 'Диагностика')
    expect(diagnosticsButton).toBeDefined()

    await diagnosticsButton!.trigger('click')
    expect(wrapper.emitted('run-diagnostics')).toHaveLength(1)
  })

  it('не показывает управление циклом — оно во вкладке «Цикл»', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, { props: baseProps })
    expect(wrapper.text()).not.toContain('Управление циклом')
    expect(wrapper.text()).not.toContain('Пауза')
    expect(wrapper.text()).not.toContain('Прервать цикл')
  })

  it('показывает подсказку про Диагностика когда manual без активной задачи', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, {
      props: {
        ...baseProps,
        automationControlMode: 'manual',
        workflowPhase: 'idle',
        currentStage: null,
      },
    })

    expect(wrapper.text()).toContain('Диагностика')
    expect(wrapper.text()).not.toContain('Для текущей стадии workflow нет доступных ручных шагов.')
  })

  it('выводит manual-step из allowed_manual_steps', async () => {
    const wrapper = mount(ZoneAutomationOpsPanel, {
      props: {
        ...baseProps,
        allowedManualSteps: ['clean_fill_start', 'irrigation_stop'],
      },
    })

    expect(wrapper.text()).toContain('Набрать чистую воду')
    expect(wrapper.text()).toContain('Стоп полива')

    const startButton = wrapper.findAll('button').find((btn) => btn.text() === 'Набрать чистую воду')
    await startButton!.trigger('click')
    expect(wrapper.emitted('run-manual-step')?.[0]).toEqual(['clean_fill_start'])
  })

  it('разрешает gate-шаги solution_change в режиме auto', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, {
      props: {
        ...baseProps,
        automationControlMode: 'auto',
        allowedManualSteps: ['solution_drain_confirm', 'solution_change_abort'],
      },
    })

    const confirmButton = wrapper.findAll('button').find((btn) => btn.text() === 'Подтвердить слив')
    expect(confirmButton).toBeDefined()
    expect(confirmButton?.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('gate-шаги solution_change доступны')
  })

  it('в auto без allowed_manual_steps показывает, что шаги недоступны', () => {
    const wrapper = mount(ZoneAutomationOpsPanel, {
      props: {
        ...baseProps,
        automationControlMode: 'auto',
        allowedManualSteps: [],
      },
    })

    expect(wrapper.text()).toContain('недоступны в режиме')
    expect(wrapper.findAll('button').some((btn) => btn.text() === 'Набрать чистую воду')).toBe(false)
  })
})
