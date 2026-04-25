import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DiffPreview from '../DiffPreview.vue'

function render(current: Record<string, unknown>, next: Record<string, unknown>) {
  return mount(DiffPreview, { props: { current, next } })
}

describe('DiffPreview', () => {
  it('shows empty state when no changes', () => {
    const w = render({ a: 1 }, { a: 1 })
    expect(w.text()).toContain('Overrides не заданы')
  })

  it('renders replace operation', () => {
    const w = render({ a: 1 }, { a: 2 })
    const rows = w.findAll('[data-op]')
    expect(rows).toHaveLength(1)
    expect(rows[0].attributes('data-op')).toBe('replace')
    expect(rows[0].text()).toContain('1')
    expect(rows[0].text()).toContain('2')
  })

  it('renders add operation', () => {
    const w = render({}, { b: 'new' })
    const rows = w.findAll('[data-op]')
    expect(rows[0].attributes('data-op')).toBe('add')
    expect(rows[0].text()).toContain('new')
  })

  it('renders remove operation', () => {
    const w = render({ b: 'old' }, {})
    const rows = w.findAll('[data-op]')
    expect(rows[0].attributes('data-op')).toBe('remove')
    expect(rows[0].text()).toContain('old')
  })

  it('strips undefined values from inputs', () => {
    const w = render({ a: 1, b: undefined }, { a: 1 })
    expect(w.text()).toContain('Overrides не заданы')
  })

  it('diffs deeply nested overrides', () => {
    const w = render(
      { irrigation: { mode: 'TIME', interval_sec: 300 } },
      { irrigation: { mode: 'TIME', interval_sec: 600 } },
    )
    const rows = w.findAll('[data-op]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('/irrigation/interval_sec')
    expect(rows[0].text()).toContain('300')
    expect(rows[0].text()).toContain('600')
  })

  it('handles added nested keys', () => {
    const w = render({ overrides: {} }, { overrides: { irrigation: { mode: 'TIME' } } })
    expect(w.findAll('[data-op]').length).toBeGreaterThan(0)
  })

  it('shows object values as JSON string', () => {
    const w = render({}, { overrides: { climate: { day_air_temp_c: 25 } } })
    expect(w.text()).toContain('day_air_temp_c')
  })
})
