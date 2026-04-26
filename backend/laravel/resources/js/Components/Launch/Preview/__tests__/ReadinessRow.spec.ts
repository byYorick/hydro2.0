import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ReadinessRow from '../ReadinessRow.vue'

describe('ReadinessRow', () => {
  it('renders label and ✓ for ok', () => {
    const w = mount(ReadinessRow, {
      props: { label: 'Теплица выбрана', status: 'ok' },
    })
    expect(w.text()).toContain('Теплица выбрана')
    expect(w.text()).toContain('✓')
    expect(w.html()).toContain('text-growth')
  })

  it('renders ! for warn', () => {
    const w = mount(ReadinessRow, { props: { label: 'X', status: 'warn' } })
    expect(w.text()).toContain('!')
    expect(w.html()).toContain('text-warn')
  })

  it('renders × for err', () => {
    const w = mount(ReadinessRow, { props: { label: 'X', status: 'err' } })
    expect(w.text()).toContain('×')
    expect(w.html()).toContain('text-alert')
  })

  it('renders note when provided', () => {
    const w = mount(ReadinessRow, {
      props: { label: 'Контуры', status: 'warn', note: '2/3' },
    })
    expect(w.text()).toContain('2/3')
  })
})
