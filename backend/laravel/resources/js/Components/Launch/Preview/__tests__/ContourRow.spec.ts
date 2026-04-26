import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ContourRow from '../ContourRow.vue'

describe('ContourRow', () => {
  it('renders label + node + bound chip when bound=true', () => {
    const w = mount(ContourRow, {
      props: { label: 'Полив', node: 'irrigation-a', bound: true },
    })
    expect(w.text()).toContain('Полив')
    expect(w.text()).toContain('irrigation-a')
    expect(w.text()).toContain('привязано')
  })

  it('renders fallback "не задано" when node is null', () => {
    const w = mount(ContourRow, { props: { label: 'pH', bound: false } })
    expect(w.text()).toContain('не задано')
  })

  it('uses warn tone when not bound', () => {
    const w = mount(ContourRow, { props: { label: 'EC', bound: false } })
    expect(w.html()).toContain('bg-warn')
  })

  it('uses growth tone when bound', () => {
    const w = mount(ContourRow, {
      props: { label: 'Полив', node: 'foo', bound: true },
    })
    expect(w.html()).toContain('bg-growth')
  })
})
