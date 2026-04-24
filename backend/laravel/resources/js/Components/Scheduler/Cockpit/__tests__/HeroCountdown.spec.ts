import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import HeroCountdown from '../HeroCountdown.vue'
import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant', 'size'],
    template: '<span class="stub-badge"><slot /></span>',
  },
}))

function buildRun(overrides: Partial<ExecutionRun> = {}): ExecutionRun {
  return {
    execution_id: 'ex-2042',
    task_id: 't-551',
    zone_id: 12,
    task_type: 'ph_correction',
    status: 'running',
    current_stage: 'dosing_acid',
    decision_config: {
      progress_steps: ['measure', 'decide', 'dose', 'stabilize', 'verify'],
      current_step: 2,
    },
    decision_strategy: 'smart_v1',
    decision_bundle_revision: '3.1.7',
    correlation_id: 'cw-118',
    ...overrides,
  }
}

describe('HeroCountdown.vue', () => {
  it('показывает пустое состояние, если нет активного run', () => {
    const wrapper = mount(HeroCountdown, { props: { run: null } })
    expect(wrapper.text()).toContain('ИСПОЛНЕНИЙ СЕЙЧАС НЕТ')
  })

  it('рендерит таймер, lane, stage и прогресс-сегменты', () => {
    const wrapper = mount(HeroCountdown, {
      props: {
        run: buildRun(),
        laneLabel: 'ph_correction',
        stageLabel: 'dosing_acid',
        etaLabel: '02:14',
        etaHint: 'осталось до завершения',
      },
    })

    expect(wrapper.text()).toContain('ИСПОЛНЯЕТСЯ')
    expect(wrapper.text()).toContain('#ex-2042')
    expect(wrapper.text()).toContain('02:14')
    expect(wrapper.text()).toContain('осталось до завершения')
    expect(wrapper.text()).toContain('dosing_acid')
    // Прогресс-бар: 5 сегментов, 3 первых активны.
    const segments = wrapper.findAll('[class*="flex-1"][class*="rounded-sm"]')
    expect(segments).toHaveLength(5)
    expect(wrapper.text()).toContain('bundle 3.1.7')
    expect(wrapper.text()).toContain('cw-118')
  })
})
