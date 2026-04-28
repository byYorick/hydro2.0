import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Select from '../Select.vue'

describe('Select', () => {
  it('renders options from string array', () => {
    const w = mount(Select, {
      props: { modelValue: 'a', options: ['a', 'b', 'c'] },
    })
    const opts = w.findAll('option')
    expect(opts).toHaveLength(3)
    expect(opts[0].text()).toBe('a')
  })

  it('renders options from {value,label} array + placeholder', () => {
    const w = mount(Select, {
      props: {
        modelValue: null,
        options: [
          { value: 1, label: 'One' },
          { value: 2, label: 'Two' },
        ],
        placeholder: '— выберите —',
      },
    })
    const opts = w.findAll('option')
    expect(opts).toHaveLength(3)
    expect(opts[0].text()).toBe('— выберите —')
    expect(opts[0].attributes('value')).toBe('')
    expect(opts[1].text()).toBe('One')
  })

  it('emits update:modelValue on change', async () => {
    const w = mount(Select, {
      props: { modelValue: 'a', options: ['a', 'b'] },
    })
    await w.find('select').setValue('b')
    const events = w.emitted('update:modelValue')
    expect(events).toBeTruthy()
    expect(events![0]).toEqual(['b'])
  })

  it('applies invalid border class', () => {
    const w = mount(Select, {
      props: { modelValue: 'a', options: ['a'], invalid: true },
    })
    expect(w.find('select').classes()).toContain('border-alert')
    expect(w.find('select').classes()).toContain('focus:border-alert')
  })

  it('disables select when disabled', () => {
    const w = mount(Select, {
      props: { modelValue: 'a', options: ['a'], disabled: true },
    })
    const select = w.find('select')
    expect(select.attributes('disabled')).toBeDefined()
    expect(select.classes()).toContain('opacity-100')
    expect(select.classes()).not.toContain('opacity-50')
  })

  it('uses brand focus classes instead of browser-default blue focus', () => {
    const w = mount(Select, {
      props: { modelValue: 'a', options: ['a'] },
    })
    const classes = w.find('select').classes()
    expect(classes).toContain('focus:border-brand')
    expect(classes).toContain('focus:ring-brand-soft')
  })
})
