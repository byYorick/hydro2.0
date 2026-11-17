import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import SwimlaneTimeline from '../SwimlaneTimeline.vue'
import type { LaneHistory } from '@/composables/zoneScheduleWorkspaceTypes'

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant', 'size'],
    template: '<span class="stub-badge"><slot /></span>',
  },
}))

describe('SwimlaneTimeline.vue', () => {
  it('рендерит пустое состояние, если lanes пустые', () => {
    const wrapper = mount(SwimlaneTimeline, {
      props: { lanes: [], horizon: '24h' },
    })
    expect(wrapper.text()).toContain('ещё нет исполнений')
  })

  it('рендерит swimlane с точками по lanes', () => {
    const lanes: LaneHistory[] = [
      {
        lane: 'irrigation',
        runs: [
          { t: 10, s: 'ok', kind: 'executed', execution_id: 'a', at: '2026-02-10T10:00:00.000Z' },
          { t: 45, s: 'run', kind: 'executed', execution_id: 'b', at: '2026-02-10T11:00:00.000Z' },
          { t: 88, s: 'warn', kind: 'planned', at: '2026-02-10T18:00:00.000Z' },
        ],
      },
      { lane: 'ph_correction', runs: [{ t: 30, s: 'err', kind: 'executed', execution_id: 'c', at: '2026-02-10T09:00:00.000Z' }] },
    ]
    const wrapper = mount(SwimlaneTimeline, {
      props: { lanes, horizon: '24h' },
    })

    expect(wrapper.text()).toContain('История и план')
    expect(wrapper.text()).toContain('Полив')
    expect(wrapper.text()).toContain('Коррекция pH')
    // «run»-точка шире, чем обычные: в компоненте задаётся `w-[18px]`.
    const runDot = wrapper.findAll('button.w-\\[18px\\]')
    expect(runDot.length).toBeGreaterThan(0)
    expect(wrapper.findAll('.swim-point--planned').length).toBe(1)
  })

  it('показывает подпись горизонта для 7d', () => {
    const wrapper = mount(SwimlaneTimeline, {
      props: { lanes: [], horizon: '7d' },
    })
    expect(wrapper.text()).toContain('3.5д назад')
  })
})

it('opens a recorded execution through a keyboard-accessible timeline button', async () => {
  const wrapper = mount(SwimlaneTimeline, { props: { horizon: '24h', lanes: [{ lane: 'irrigation', runs: [{ t: 45, s: 'ok', kind: 'executed', execution_id: '91', at: '2026-11-17T08:00:00Z' }] }] } })
  const point = wrapper.get('button.swim-point')
  expect(point.attributes('aria-label')).toContain('#91')
  await point.trigger('click')
  expect(wrapper.emitted('select')?.[0]).toEqual(['91'])
})
