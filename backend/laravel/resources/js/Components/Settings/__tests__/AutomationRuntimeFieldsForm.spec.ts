import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AutomationRuntimeFieldsForm from '@/Components/Settings/AutomationRuntimeFieldsForm.vue'
import type { AutomationRuntimeSettingSection } from '@/types/SystemSettings'

const sections: AutomationRuntimeSettingSection[] = [
  {
    key: 'scheduler_runtime',
    title: 'Планировщик задач',
    items: [
      {
        key: 'automation_engine.scheduler_due_grace_sec',
        label: 'Допуск опоздания задачи',
        description: 'Насколько раньше срока задачу уже можно отправлять в работу.',
        value: 15,
        source: 'default',
        editable: true,
        advanced: false,
        type: 'int',
        input_type: 'number',
        unit: 'сек',
      },
      {
        key: 'automation_engine.scheduler_lock_key',
        label: 'Ключ блокировки',
        description: 'Имя общей блокировки dispatcher.',
        value: 'automation:dispatch-schedules',
        source: 'override',
        editable: true,
        advanced: true,
        type: 'string',
        input_type: 'text',
      },
    ],
  },
]

function mountForm() {
  return mount(AutomationRuntimeFieldsForm, {
    props: {
      sections,
      modelValue: {
        'automation_engine.scheduler_due_grace_sec': 15,
        'automation_engine.scheduler_lock_key': 'automation:dispatch-schedules',
      },
    },
  })
}

describe('AutomationRuntimeFieldsForm', () => {
  it('скрывает технические параметры до явного запроса', async () => {
    const wrapper = mountForm()

    expect(wrapper.text()).toContain('Допуск опоздания задачи')
    expect(wrapper.text()).not.toContain('Ключ блокировки')

    await wrapper.get('[data-testid="automation-runtime-advanced-toggle"]').trigger('click')

    expect(wrapper.text()).toContain('Ключ блокировки')
  })

  it('находит скрытый технический параметр поиском', async () => {
    const wrapper = mountForm()

    await wrapper.get('[data-testid="automation-runtime-search"]').setValue('блокировки')

    expect(wrapper.text()).toContain('Ключ блокировки')
    expect(wrapper.text()).not.toContain('Допуск опоздания задачи')
  })

  it('отделяет сохранённые overrides от несохранённых правок', async () => {
    const wrapper = mountForm()

    await wrapper.get('[data-testid="automation-runtime-advanced-toggle"]').trigger('click')

    expect(
      wrapper
        .find('[data-testid="settings-automation-field-automation_engine.scheduler_lock_key-changed"]')
        .exists(),
    ).toBe(false)
    expect(wrapper.get('[data-testid="automation-runtime-overrides-count"]').text()).toContain('1')
    expect(wrapper.find('[data-testid="automation-runtime-changed-count"]').exists()).toBe(false)
    await wrapper.get('[data-testid="settings-automation-engine-input-automation_engine.scheduler_due_grace_sec"]').setValue('42')
    expect(wrapper.get('[data-testid="automation-runtime-changed-count"]').text()).toContain('1')
    await wrapper.get('[data-testid="automation-runtime-filter-changed"]').trigger('click')
    expect(wrapper.text()).toContain('Допуск опоздания задачи')
    expect(wrapper.text()).not.toContain('Ключ блокировки')
  })

  it('передаёт изменения поля наверх', async () => {
    const wrapper = mountForm()

    await wrapper
      .get('[data-testid="settings-automation-engine-input-automation_engine.scheduler_due_grace_sec"]')
      .setValue('42')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted?.at(-1)?.[0]).toMatchObject({
      'automation_engine.scheduler_due_grace_sec': 42,
    })
  })
})
