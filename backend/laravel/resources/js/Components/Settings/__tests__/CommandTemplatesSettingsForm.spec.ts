import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CommandTemplatesSettingsForm from '../CommandTemplatesSettingsForm.vue'
import type { AutomationCommandTemplateStep } from '@/types/SystemSettings'

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'size', 'type'],
    emits: ['click'],
    template: '<button :disabled="disabled" :type="type" @click="$emit(\'click\')"><slot /></button>',
  },
}))

describe('CommandTemplatesSettingsForm.vue', () => {
  const fields = [
    {
      path: 'irrigation_start',
      label: 'irrigation_start',
      description: 'Команды запуска irrigation.',
      type: 'json' as const,
    },
  ]

  const modelValue: Record<string, AutomationCommandTemplateStep[]> = {
    irrigation_start: [
      { channel: 'pump_main', cmd: 'set_relay', params: { state: true } },
    ],
  }

  it('рендерит шаги команд вместо сырого JSON', () => {
    const wrapper = mount(CommandTemplatesSettingsForm, {
      props: {
        fields,
        modelValue,
      },
    })

    expect(wrapper.text()).toContain('Полив — запуск')
    expect(wrapper.find('[data-testid="command-template-channel-irrigation_start-0"]').element).toHaveProperty('value', 'pump_main')
    expect(wrapper.find('[data-testid="command-template-state-irrigation_start-0"]').element).toHaveProperty('value', 'true')
  })

  it('добавляет новый шаг и эмитит обновлённый draft', async () => {
    const wrapper = mount(CommandTemplatesSettingsForm, {
      props: {
        fields,
        modelValue,
      },
    })

    await wrapper.find('[data-testid="command-template-add-irrigation_start"]').trigger('click')

    const updates = wrapper.emitted('update:modelValue')
    expect(updates?.length).toBeGreaterThan(0)
    const last = updates?.[updates.length - 1]?.[0] as Record<string, AutomationCommandTemplateStep[]>
    expect(last.irrigation_start).toHaveLength(2)
    expect(last.irrigation_start[1]).toMatchObject({
      channel: '',
      cmd: 'set_relay',
      params: { state: true },
    })
  })
})
