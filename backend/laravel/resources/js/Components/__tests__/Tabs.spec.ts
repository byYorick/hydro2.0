import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Tabs from '../Tabs.vue'

describe('Tabs.vue', () => {
  it('emits update on click', async () => {
    const wrapper = mount(Tabs, {
      props: {
        modelValue: 'overview',
        tabs: [
          { id: 'overview', label: 'Overview' },
          { id: 'events', label: 'Events' },
        ],
      },
    })

    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['events'])
  })

  it('skips disabled tabs on arrow navigation', async () => {
    const wrapper = mount(Tabs, {
      props: {
        modelValue: 'overview',
        tabs: [
          { id: 'overview', label: 'Overview' },
          { id: 'cycle', label: 'Cycle', disabled: true },
          { id: 'events', label: 'Events' },
        ],
      },
    })

    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('keydown', { key: 'ArrowRight' })

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['events'])
  })

  it('does not emit when clicking disabled tab', async () => {
    const wrapper = mount(Tabs, {
      props: {
        modelValue: 'overview',
        tabs: [
          { id: 'overview', label: 'Overview' },
          { id: 'cycle', label: 'Cycle', disabled: true },
        ],
      },
    })

    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
  })
})
