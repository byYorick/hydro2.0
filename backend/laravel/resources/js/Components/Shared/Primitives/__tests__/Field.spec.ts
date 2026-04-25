import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Field from '../Field.vue'

describe('Field', () => {
  it('renders label text', () => {
    const w = mount(Field, { props: { label: 'Зона' } })
    expect(w.text()).toContain('Зона')
  })

  it('renders required asterisk when required', () => {
    const w = mount(Field, { props: { label: 'Зона', required: true } })
    expect(w.text()).toContain('*')
    expect(w.find('.text-alert').exists()).toBe(true)
  })

  it('renders hint when no error', () => {
    const w = mount(Field, { props: { label: 'X', hint: 'подсказка' } })
    expect(w.text()).toContain('подсказка')
  })

  it('renders error and hides hint', () => {
    const w = mount(Field, {
      props: { label: 'X', hint: 'подсказка', error: 'ошибка' },
    })
    expect(w.text()).toContain('ошибка')
    expect(w.text()).not.toContain('подсказка')
  })

  it('renders default slot', () => {
    const w = mount(Field, {
      props: { label: 'X' },
      slots: { default: '<input data-test="inner" />' },
    })
    expect(w.find('[data-test="inner"]').exists()).toBe(true)
  })
})
