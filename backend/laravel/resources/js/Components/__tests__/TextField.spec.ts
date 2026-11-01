import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TextField from '../TextField.vue'
import SelectField from '../SelectField.vue'

describe('TextField', () => {
  it('связывает значение и показывает ошибку', async () => {
    const wrapper = mount(TextField, {
      props: {
        modelValue: 'ph',
        label: 'Поиск',
        error: 'Слишком коротко',
        'onUpdate:modelValue': () => undefined,
      },
      attrs: { placeholder: 'зона' },
    })

    const input = wrapper.get('input')
    expect(input.element.value).toBe('ph')
    expect(input.attributes('placeholder')).toBe('зона')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(wrapper.text()).toContain('Слишком коротко')
    expect(wrapper.text()).toContain('Поиск')

    await input.setValue('ec')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['ec'])
  })
})

describe('SelectField', () => {
  it('рендерит опции и отдаёт выбранное значение', async () => {
    const wrapper = mount(SelectField, {
      props: {
        modelValue: 'warning',
        label: 'Критичность',
        'onUpdate:modelValue': () => undefined,
      },
      slots: {
        default: '<option value="warning">Предупреждение</option><option value="critical">Тревога</option>',
      },
    })

    const select = wrapper.get('select')
    expect(select.element.value).toBe('warning')
    await select.setValue('critical')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['critical'])
  })
})
