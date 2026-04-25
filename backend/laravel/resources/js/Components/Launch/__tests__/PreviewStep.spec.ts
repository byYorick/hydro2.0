import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import PreviewStep from '../PreviewStep.vue'
import {
  _resetLaunchPreferencesForTests,
} from '@/composables/useLaunchPreferences'

describe('PreviewStep', () => {
  beforeEach(() => {
    localStorage.clear()
    _resetLaunchPreferencesForTests()
  })

  it('renders summary stats from payloadPreview', () => {
    const w = mount(PreviewStep, {
      props: {
        payloadPreview: {
          zone_id: 4,
          recipe_revision_id: 7,
          plant_id: 2,
          planting_at: '2026-04-25T12:00:00.000Z',
          batch_label: 'batch-04',
        },
        errors: [],
      },
    })
    expect(w.text()).toContain('Сводка запуска')
    expect(w.text()).toContain('4')
    expect(w.text()).toContain('7')
    expect(w.text()).toContain('batch-04')
  })

  it('shows готова chip when no errors', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: { zone_id: 1 }, errors: [] },
    })
    expect(w.text()).toContain('готова')
    expect(w.text()).toContain('Все проверки пройдены')
  })

  it('shows errors chip + readiness list when errors present', () => {
    const w = mount(PreviewStep, {
      props: {
        payloadPreview: { zone_id: 1 },
        errors: [
          { path: 'zone_id', message: 'обязательное' },
          { path: 'planting_at', message: 'некорректная дата' },
        ],
      },
    })
    expect(w.text()).toContain('2 ошибок')
    expect(w.text()).toContain('zone_id')
    expect(w.text()).toContain('обязательное')
    expect(w.text()).toContain('planting_at')
    expect(w.text()).toContain('некорректная дата')
  })

  it('renders RecipePhasesSummary card only when recipePhases provided', () => {
    const w1 = mount(PreviewStep, {
      props: { payloadPreview: {}, errors: [], recipePhases: [] },
    })
    expect(w1.text()).not.toContain('Фазы рецепта')

    const w2 = mount(PreviewStep, {
      props: {
        payloadPreview: {},
        errors: [],
        recipePhases: [{ name: 'Vegetative', duration_hours: 24 }],
      },
    })
    expect(w2.text()).toContain('Фазы рецепта')
  })

  it('exposes diff-preview slot', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: {}, errors: [] },
      slots: { 'diff-preview': '<div data-test="diff">DIFF</div>' },
    })
    expect(w.find('[data-test="diff"]').exists()).toBe(true)
  })

  it('formats planting_at as YYYY-MM-DD HH:MM', () => {
    const w = mount(PreviewStep, {
      props: {
        payloadPreview: { planting_at: '2026-04-25T08:30:00.000Z' },
        errors: [],
      },
    })
    // Local timezone-dependent — we just assert format pattern
    expect(w.text()).toMatch(/2026-04-25 \d{2}:\d{2}/)
  })

  it('hint text mentions POST /grow-cycles endpoint', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: {}, errors: [] },
    })
    expect(w.text()).toContain('/api/zones/{id}/grow-cycles')
  })
})
