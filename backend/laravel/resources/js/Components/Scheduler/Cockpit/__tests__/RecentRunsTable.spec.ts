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
  it('фильтрует историю по статусу и поиску и сообщает доступные строки для клавиатуры', async () => {
    const wrapper = mount(RecentRunsTable, { props: { showFilters: true, runs: [
      run({ execution_id: 'failed-1', status: 'failed', is_active: false }),
      run({ execution_id: 'done-2', status: 'completed', is_active: false }),
    ] } })
    await wrapper.get('[data-testid="scheduler-history-status"]').setValue('failed')
    expect(wrapper.findAll('[data-testid^="scheduler-runs-row-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="scheduler-runs-row-failed-1"]').exists()).toBe(true)
    await wrapper.get('[data-testid="scheduler-history-search"]').setValue('nothing')
    expect(wrapper.text()).toContain('По выбранным условиям запусков нет')
    expect(wrapper.emitted('visible-runs')?.at(-1)).toEqual([[]])
    wrapper.unmount()
  })
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

  it('показывает chemistry warning для completed run с недостигнутыми целями', () => {
    const wrapper = mount(RecentRunsTable, {
      props: {
        runs: [run({
          execution_id: 'ex-chem-1',
          status: 'completed',
          is_active: false,
          chemistry_outcome: 'targets_not_achieved',
        })],
      },
    })

    expect(wrapper.get('[data-testid="scheduler-runs-chemistry-ex-chem-1"]').text())
      .toContain('цели не достигнуты')
  })
})
