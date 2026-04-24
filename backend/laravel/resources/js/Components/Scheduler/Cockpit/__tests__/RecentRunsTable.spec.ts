import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import RecentRunsTable from '../RecentRunsTable.vue'
import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant', 'size'],
    template: '<span class="stub-badge"><slot /></span>',
  },
}))

function run(overrides: Partial<ExecutionRun> = {}): ExecutionRun {
  return {
    execution_id: 'ex-2042',
    task_id: 't-551',
    zone_id: 12,
    task_type: 'ph_correction',
    status: 'running',
    is_active: true,
    decision_outcome: 'run',
    decision_reason_code: 'dosing',
    correlation_id: 'cw-118',
    timeline: [],
    accepted_at: '2026-02-10T12:30:00Z',
    completed_at: '2026-02-10T12:32:14Z',
    ...overrides,
  }
}

describe('RecentRunsTable.vue', () => {
  it('рендерит пустое состояние', () => {
    const wrapper = mount(RecentRunsTable, { props: { runs: [] } })
    expect(wrapper.text()).toContain('Пока нет исполнений')
  })

  it('рендерит строки и эмитит select по клику', async () => {
    const wrapper = mount(RecentRunsTable, {
      props: {
        runs: [
          run({ execution_id: 'ex-2042' }),
          run({ execution_id: 'ex-2041', status: 'completed', is_active: false }),
        ],
        selectedId: 'ex-2042',
      },
    })

    const rows = wrapper.findAll('[data-testid^="scheduler-runs-row-"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].attributes('data-selected')).toBe('true')
    expect(rows[1].attributes('data-selected')).toBe('false')

    await rows[1].trigger('click')
    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]).toEqual(['ex-2041'])
  })

  it('использует переданный decisionLabel для построения колонки', () => {
    const wrapper = mount(RecentRunsTable, {
      props: {
        runs: [run({ execution_id: 'ex-9000' })],
        decisionLabel: () => 'CUSTOM · label',
      },
    })
    expect(wrapper.text()).toContain('CUSTOM · label')
  })
})
