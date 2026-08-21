import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PresetPillStrip from '../PresetPillStrip.vue'

describe('PresetPillStrip.vue', () => {
  it('рендерит крупные плашки и эмитит select', async () => {
    const wrapper = mount(PresetPillStrip, {
      props: {
        modelValue: null,
        items: [
          { key: null, label: 'Системный пресет', meta: 'system', locked: true, testId: 'pill-system' },
          { key: 7, label: 'Custom', meta: 'custom', testId: 'pill-custom' },
        ],
      },
    })

    expect(wrapper.get('[data-testid="preset-pill-strip"]').text()).toContain('Пресет')
    expect(wrapper.get('[data-testid="pill-system"]').text()).toContain('Системный')
    expect(wrapper.get('[data-testid="pill-system"]').classes().join(' ')).toContain('rounded-sm')
    expect(wrapper.get('[data-testid="pill-system"]').classes().join(' ')).toContain('min-w-[120px]')

    await wrapper.get('[data-testid="pill-custom"]').trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual([7])
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([7])
    expect(wrapper.get('[data-testid="pill-custom"]').classes().join(' ')).not.toContain('bg-brand')
  })

  it('подсвечивает активную плашку brand-цветом', () => {
    const wrapper = mount(PresetPillStrip, {
      props: {
        modelValue: 7,
        items: [
          { key: null, label: 'Системный пресет', meta: 'system', testId: 'pill-system' },
          { key: 7, label: 'Custom', meta: 'custom', testId: 'pill-custom' },
        ],
      },
    })

    expect(wrapper.get('[data-testid="pill-custom"]').classes().join(' ')).toContain('bg-brand')
  })
})
