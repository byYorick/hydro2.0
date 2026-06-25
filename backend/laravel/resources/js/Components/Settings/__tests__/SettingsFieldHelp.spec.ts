import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SettingsFieldHelp from '../SettingsFieldHelp.vue'

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'size', 'type'],
    emits: ['click'],
    template: '<button :type="type" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/Components/Modal.vue', () => ({
  default: {
    name: 'Modal',
    props: ['open', 'title', 'size', 'hideDefaultCancel'],
    emits: ['close'],
    template: '<div v-if="open" :data-testid="$attrs[\'data-testid\']"><slot /><slot name="footer" /></div>',
  },
}))

describe('SettingsFieldHelp.vue', () => {
  it('открывает модальное окно с подробным текстом на русском', async () => {
    const wrapper = mount(SettingsFieldHelp, {
      props: {
        title: 'Waiting command — warning',
        summary: 'Краткое описание.',
        help: 'Подробное описание порога warning для оператора.',
      },
    })

    expect(wrapper.find('[data-testid="settings-field-help-modal"]').exists()).toBe(false)

    await wrapper.find('[data-testid="settings-field-help"]').trigger('click')

    expect(wrapper.find('[data-testid="settings-field-help-modal"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Подробное описание порога warning для оператора.')
    expect(wrapper.text()).toContain('Краткое описание.')
  })
})
