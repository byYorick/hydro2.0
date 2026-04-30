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

    expect(wrapper.text()).toContain('Лента исполнений')
    expect(wrapper.text()).toContain('irrigation')
    expect(wrapper.text()).toContain('ph_correction')
    // «run»-точка шире, чем обычные: в компоненте задаётся `w-[18px]`.
    const runDot = wrapper.findAll('div.w-\\[18px\\]')
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
