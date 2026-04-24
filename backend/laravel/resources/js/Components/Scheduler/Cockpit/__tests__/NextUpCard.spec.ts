import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import NextUpCard from '../NextUpCard.vue'
import type { PlanWindow } from '@/composables/zoneScheduleWorkspaceTypes'

function window(overrides: Partial<PlanWindow>): PlanWindow {
  return {
    plan_window_id: 'w-1',
    zone_id: 42,
    task_type: 'irrigation',
    label: 'Полив',
    schedule_key: 'zone:42|type:irrigation',
    trigger_at: '2026-02-10T09:00:00Z',
    origin: 'effective_targets',
    state: 'planned',
    mode: 'interval',
    ...overrides,
  }
}

describe('NextUpCard.vue', () => {
  it('рендерит пустое состояние, если окон нет', () => {
    const wrapper = mount(NextUpCard, { props: { windows: [] } })
    expect(wrapper.text()).toContain('нет запланированных окон')
  })

  it('рендерит максимум `maxItems` окон и подсвечивает первое', () => {
    const wrapper = mount(NextUpCard, {
      props: {
        windows: [
          window({ plan_window_id: 'w-1', task_type: 'irrigation', trigger_at: '2026-02-10T12:38:00Z' }),
          window({ plan_window_id: 'w-2', task_type: 'ph_correction', trigger_at: '2026-02-10T12:52:00Z' }),
          window({ plan_window_id: 'w-3', task_type: 'lighting_tick', trigger_at: '2026-02-10T13:21:00Z' }),
          window({ plan_window_id: 'w-4', task_type: 'diagnostics', trigger_at: '2026-02-10T14:00:00Z' }),
        ],
        maxItems: 3,
        formatDateTime: (value) => `@${value}`,
        formatRelative: () => '4м',
        laneLabel: (t) => `lane:${t}`,
      },
    })

    const rows = wrapper.findAll('[data-testid^="scheduler-next-up-row-"]')
    expect(rows).toHaveLength(3)
    expect(rows[0].text()).toContain('lane:irrigation')
    expect(rows[0].text()).toContain('@2026-02-10T12:38:00Z')
    expect(rows[0].text()).toContain('4м')
  })
})
