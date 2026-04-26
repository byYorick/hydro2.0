import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CalibrationSidebar from '../CalibrationSidebar.vue'
import type { CalibrationNavMap } from '../CalibrationSidebar.vue'

const baseNav: CalibrationNavMap = {
  sensors: { state: 'passed', count: '2/2' },
  pumps: { state: 'blocker', count: '2/6' },
  process: { state: 'waiting', count: '0/4', waitingLabel: 'ждёт насосы' },
  correction: { state: 'optional', count: 'опц.' },
  pid: { state: 'optional', count: 'опц.' },
}

describe('CalibrationSidebar', () => {
  it('renders 5 nav items in 2 groups', () => {
    const w = mount(CalibrationSidebar, {
      props: { current: 'pumps', nav: baseNav },
    })
    expect(w.text()).toContain('Базовая калибровка')
    expect(w.text()).toContain('Тонкая настройка')
    expect(w.text()).toContain('Сенсоры')
    expect(w.text()).toContain('Насосы')
    expect(w.text()).toContain('Процесс')
    expect(w.text()).toContain('Коррекция')
    expect(w.text()).toContain('PID и autotune')
  })

  it('shows ✓/!/⏳ icons by state', () => {
    const w = mount(CalibrationSidebar, {
      props: { current: 'pumps', nav: baseNav },
    })
    const html = w.html()
    expect(html).toContain('✓') // sensors passed
    expect(html).toContain('!') // pumps blocker
    expect(html).toContain('⏳') // process waiting
  })

  it('emits select(id) on click', async () => {
    const w = mount(CalibrationSidebar, {
      props: { current: 'pumps', nav: baseNav },
    })
    const sensorsBtn = w
      .findAll('button')
      .find((b) => b.text().includes('Сенсоры'))!
    await sensorsBtn.trigger('click')
    expect(w.emitted('select')![0]).toEqual(['sensors'])
  })

  it('marks current with aria-current="page"', () => {
    const w = mount(CalibrationSidebar, {
      props: { current: 'pid', nav: baseNav },
    })
    const pidBtn = w.findAll('button').find((b) => b.text().includes('PID'))!
    expect(pidBtn.attributes('aria-current')).toBe('page')
  })

  it('appends waitingLabel to subtitle', () => {
    const w = mount(CalibrationSidebar, {
      props: { current: 'pumps', nav: baseNav },
    })
    expect(w.text()).toContain('ждёт насосы')
  })
})
