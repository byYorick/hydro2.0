import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DayNightStrip from '../DayNightStrip.vue'

describe('DayNightStrip', () => {
  it('renders 5 hour markers (00 / 06 / 12 / 18 / 24)', () => {
    const w = mount(DayNightStrip)
    expect(w.text()).toContain('00:00')
    expect(w.text()).toContain('06:00')
    expect(w.text()).toContain('12:00')
    expect(w.text()).toContain('18:00')
    expect(w.text()).toContain('24:00')
  })

  it('renders день range with luxDay', () => {
    const w = mount(DayNightStrip, {
      props: { scheduleStart: '07:30', scheduleEnd: '20:00', luxDay: 30000 },
    })
    expect(w.text()).toContain('07:30–20:00')
    expect(w.text()).toContain('30000 lux')
  })

  it('renders night lux value when provided', () => {
    const w = mount(DayNightStrip, {
      props: { scheduleStart: '06:00', scheduleEnd: '18:00', luxNight: 100 },
    })
    expect(w.text()).toContain('Ночь')
    expect(w.text()).toContain('100')
  })

  it('applies opacity when not enabled', () => {
    const w = mount(DayNightStrip, { props: { enabled: false } })
    expect(w.html()).toContain('opacity-55')
  })

  it('handles invalid time strings without throwing', () => {
    const w = mount(DayNightStrip, {
      props: { scheduleStart: 'invalid', scheduleEnd: 'broken' },
    })
    expect(w.find('div').exists()).toBe(true)
  })
})
