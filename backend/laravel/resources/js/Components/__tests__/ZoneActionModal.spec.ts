import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ZoneActionModal from '../ZoneActionModal.vue'

// Mock dependencies
vi.mock('@/Components/Modal.vue', () => ({
  default: {
    name: 'Modal',
    props: ['open', 'title'],
    emits: ['close'],
    template: `
      <div v-if="open" class="modal">
        <div class="modal-title">{{ title }}</div>
        <slot />
        <slot name="footer" />
      </div>
    `
  }
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['variant', 'disabled', 'type'],
    template: '<button :disabled="disabled"><slot /></button>'
  }
}))

describe('ZoneActionModal', () => {
  it('renders modal when show is true', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_IRRIGATION',
        zoneId: 1
      }
    })

    expect(wrapper.find('.modal').exists()).toBe(true)
  })

  it('does not render modal when show is false', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: false,
        actionType: 'FORCE_IRRIGATION',
        zoneId: 1
      }
    })

    expect(wrapper.find('.modal').exists()).toBe(false)
  })

  it('displays correct title for FORCE_IRRIGATION', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_IRRIGATION',
        zoneId: 1
      }
    })

    expect(wrapper.text()).toContain('Полив зоны')
  })

  it('displays correct title for FORCE_PH_CONTROL', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_PH_CONTROL',
        zoneId: 1
      }
    })

    expect(wrapper.text()).toContain('Коррекция pH')
  })

  it('displays irrigation form fields', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_IRRIGATION',
        zoneId: 1
      }
    })

    expect(wrapper.text()).toContain('Длительность полива (секунды)')
    const input = wrapper.find('input[type="number"]')
    expect(input.exists()).toBe(true)
    expect(input.attributes('min')).toBe('1')
    expect(input.attributes('max')).toBe('3600')
  })

  it('displays pH control form fields', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_PH_CONTROL',
        zoneId: 1
      }
    })

    expect(wrapper.text()).toContain('Целевой pH')
    const input = wrapper.find('input[type="number"]')
    expect(input.exists()).toBe(true)
    expect(input.attributes('min')).toBe('4.0')
    expect(input.attributes('max')).toBe('9.0')
  })

  it('displays EC control form fields', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_EC_CONTROL',
        zoneId: 1
      }
    })

    expect(wrapper.text()).toContain('Целевой EC')
    const input = wrapper.find('input[type="number"]')
    expect(input.exists()).toBe(true)
    expect(input.attributes('min')).toBe('0.1')
    expect(input.attributes('max')).toBe('10.0')
  })

  it('displays climate control form fields', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_CLIMATE',
        zoneId: 1
      }
    })

    expect(wrapper.text()).toContain('Целевая температура')
    expect(wrapper.text()).toContain('Целевая влажность')
    const inputs = wrapper.findAll('input[type="number"]')
    expect(inputs.length).toBe(2)
  })

  it('displays lighting control form fields', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_LIGHTING',
        zoneId: 1
      }
    })

    expect(wrapper.text()).toContain('Интенсивность')
    expect(wrapper.text()).toContain('Длительность (часы)')
    const inputs = wrapper.findAll('input[type="number"]')
    expect(inputs.length).toBe(2)
  })

  it('emits submit event with correct params for FORCE_IRRIGATION', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_IRRIGATION',
        zoneId: 1
      }
    })

    const input = wrapper.find('input[type="number"]')
    await input.setValue(30)

    const form = wrapper.find('form')
    await form.trigger('submit.prevent')

    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted('submit')[0][0]).toMatchObject({
      actionType: 'FORCE_IRRIGATION',
      params: {
        duration_sec: 30
      }
    })
  })

  it('emits submit event with correct params for FORCE_PH_CONTROL', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_PH_CONTROL',
        zoneId: 1
      }
    })

    const input = wrapper.find('input[type="number"]')
    await input.setValue(6.5)

    const form = wrapper.find('form')
    await form.trigger('submit.prevent')

    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted('submit')[0][0]).toMatchObject({
      actionType: 'FORCE_PH_CONTROL',
      params: {
        target_ph: 6.5
      }
    })
  })

  it('emits close event when form is submitted', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_IRRIGATION',
        zoneId: 1
      }
    })

    const form = wrapper.find('form')
    await form.trigger('submit.prevent')

    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('applies defaultParams to form', () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: true,
        actionType: 'FORCE_IRRIGATION',
        zoneId: 1,
        defaultParams: {
          duration_sec: 60
        }
      }
    })

    const input = wrapper.find('input[type="number"]')
    expect(input.element.value).toBe('60')
  })

  it('resets form when show changes to true', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        show: false,
        actionType: 'FORCE_IRRIGATION',
        zoneId: 1
      }
    })

    await wrapper.setProps({ show: true })
    
    const input = wrapper.find('input[type="number"]')
    // Should reset to default value
    expect(input.element.value).toBe('10')
  })
})

