import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SettingsFieldRow from '@/Components/Settings/SettingsFieldRow.vue'

describe('SettingsFieldRow', () => {
  it('показывает подпись, единицу измерения и связывает label с полем', () => {
    const wrapper = mount(SettingsFieldRow, {
      props: {
        label: 'Допуск опоздания задачи',
        unit: 'сек',
        fieldId: 'field-due-grace',
        testId: 'row-due-grace',
      },
      slots: {
        default: '<input id="field-due-grace" />',
      },
    })

    expect(wrapper.text()).toContain('Допуск опоздания задачи')
    expect(wrapper.text()).toContain('сек')
    expect(wrapper.get('label').attributes('for')).toBe('field-due-grace')
  })

  it('прячет описание в подсказку, а не в строку', () => {
    const wrapper = mount(SettingsFieldRow, {
      props: {
        label: 'Порог зависания задачи',
        description: 'После этого времени планировщик закрывает зависшую задачу.',
        testId: 'row-stale',
      },
    })

    expect(wrapper.text()).not.toContain('После этого времени планировщик закрывает зависшую задачу.')
    expect(wrapper.get('[data-testid="row-stale-help"]').exists()).toBe(true)
  })

  it('отмечает изменённое значение', () => {
    const wrapper = mount(SettingsFieldRow, {
      props: {
        label: 'Ключ блокировки',
        changed: true,
        testId: 'row-lock',
      },
    })

    expect(wrapper.get('[data-testid="row-lock-changed"]').text()).toBe('изменено')
  })
})
