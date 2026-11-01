import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { applyFieldModifiers } from '../fieldValue'
import TextField from '../TextField.vue'
import SelectField from '../SelectField.vue'

describe('applyFieldModifiers', () => {
  it('обрезает строку и приводит число, оставляя пустое значение', () => {
    expect(applyFieldModifiers('  ph  ', { trim: true })).toBe('ph')
    expect(applyFieldModifiers('6.2', { number: true })).toBe(6.2)
    expect(applyFieldModifiers('', { number: true })).toBe('')
    expect(applyFieldModifiers('нет', { number: true })).toBe('нет')
  })
})

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

  it('рисует textarea, подсказку, единицу и отдаёт фокус', async () => {
    const wrapper = mount(TextField, {
      props: {
        modelValue: 'заметка',
        label: 'Заметки',
        hint: 'необязательно',
        suffix: 'мл',
        multiline: true,
        rows: 4,
        'onUpdate:modelValue': () => undefined,
      },
    })

    const area = wrapper.get('textarea')
    expect(area.attributes('rows')).toBe('4')
    expect(wrapper.text()).toContain('необязательно')
    expect(wrapper.text()).toContain('мл')
    expect(wrapper.find('input').exists()).toBe(false)

    await area.setValue('новая')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['новая'])

    const host = document.createElement('div')
    document.body.appendChild(host)
    const attached = mount(TextField, {
      props: {
        modelValue: 'заметка',
        multiline: true,
        'onUpdate:modelValue': () => undefined,
      },
      attachTo: host,
    })
    ;(attached.vm as { focus: () => void }).focus()
    expect(document.activeElement).toBe(attached.get('textarea').element)
    attached.unmount()
    host.remove()
  })

  it('приводит v-model.number и блокирует поле', async () => {
    const wrapper = mount(TextField, {
      props: {
        modelValue: 5,
        modelModifiers: { number: true },
        disabled: true,
        'onUpdate:modelValue': () => undefined,
      },
      attrs: { type: 'number' },
    })

    const input = wrapper.get('input')
    expect(input.attributes('disabled')).toBeDefined()
    expect(input.attributes('type')).toBe('number')

    await wrapper.setProps({ disabled: false })
    await input.setValue('8')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([8])
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

  it('показывает подсказку и помечает невалидное значение', () => {
    const wrapper = mount(SelectField, {
      props: {
        modelValue: '',
        hint: 'выберите контур',
        invalid: true,
        'onUpdate:modelValue': () => undefined,
      },
      slots: {
        default: '<option value="">—</option>',
      },
    })

    expect(wrapper.text()).toContain('выберите контур')
    expect(wrapper.get('select').attributes('aria-invalid')).toBe('true')
    expect(wrapper.element.tagName).toBe('DIV')
  })
})
