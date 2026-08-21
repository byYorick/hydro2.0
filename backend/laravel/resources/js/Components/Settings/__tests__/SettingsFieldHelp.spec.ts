import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import SettingsFieldHelp from '../SettingsFieldHelp.vue'

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'size', 'type'],
    emits: ['click'],
    template: '<button :type="type" @click="$emit(\'click\')"><slot /></button>',
  },
}))

describe('SettingsFieldHelp.vue', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('открывает модальное окно с подробным текстом на русском', async () => {
    const wrapper = mount(SettingsFieldHelp, {
      props: {
        title: 'Waiting command — warning',
        summary: 'Краткое описание.',
        help: 'Подробное описание порога warning для оператора.',
      },
      attachTo: document.body,
    })

    expect(document.body.querySelector('[data-testid="settings-field-help-modal"]')).toBeNull()

    await wrapper.find('[data-testid="settings-field-help"]').trigger('click')
    await nextTick()

    const modal = document.body.querySelector('[data-testid="settings-field-help-modal"]')
    expect(modal).not.toBeNull()
    expect(modal?.textContent).toContain('Подробное описание порога warning для оператора.')
    expect(modal?.textContent).toContain('Краткое описание.')
    expect(document.body.querySelector('[data-testid="app-modal-root"]')).not.toBeNull()

    wrapper.unmount()
  })
})
