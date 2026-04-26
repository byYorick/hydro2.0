import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KV from '../KV.vue'

describe('KV', () => {
  it('renders rows as key-value pairs', () => {
    const w = mount(KV, {
      props: {
        rows: [
          ['MQTT host', 'localhost'],
          ['Bridge', '9000'],
        ],
      },
    })
    expect(w.text()).toContain('MQTT host')
    expect(w.text()).toContain('localhost')
    expect(w.text()).toContain('Bridge')
    expect(w.text()).toContain('9000')
  })

  it('renders empty container for empty rows', () => {
    const w = mount(KV, { props: { rows: [] } })
    expect(w.findAll('span')).toHaveLength(0)
  })

  it('accepts numeric values', () => {
    const w = mount(KV, { props: { rows: [['count', 42]] } })
    expect(w.text()).toContain('42')
  })
})
