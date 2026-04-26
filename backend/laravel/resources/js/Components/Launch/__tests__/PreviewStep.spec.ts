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
    expect(w.text()).toContain('id 4')
    expect(w.text()).toContain('id 2')
    expect(w.text()).toContain('r7')
    expect(w.text()).toContain('batch-04')
  })

  it('shows готова chip when no errors', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: { zone_id: 1 }, errors: [] },
    })
    expect(w.text()).toContain('готова')
  })

  it('shows N ошибок chip when zod errors present', () => {
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
  })

  it('renders 9 readiness rows by default', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: { zone_id: 1 }, errors: [] },
    })
    expect(w.text()).toContain('Теплица выбрана')
    expect(w.text()).toContain('Зона создана и привязана')
    expect(w.text()).toContain('Рецепт активен')
    expect(w.text()).toContain('Контуры привязаны')
    expect(w.text()).toContain('Сенсоры откалиброваны')
    expect(w.text()).toContain('Насосы откалиброваны')
    expect(w.text()).toContain('PID pH и EC сохранены')
    expect(w.text()).toContain('Процессы настроены')
    expect(w.text()).toContain('automation-engine online')
  })

  it('renders 3 ContourRow blocks (Полив / pH / EC)', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: { zone_id: 1 }, errors: [] },
    })
    const text = w.text()
    expect(text).toContain('Контуры')
    // Заголовки контуров — с пометкой "не задано" по умолчанию (без assignments)
    expect(text.match(/не задано/g)?.length).toBeGreaterThanOrEqual(3)
  })

  it('emits launch on кнопка click when ready', async () => {
    const w = mount(PreviewStep, {
      props: {
        payloadPreview: {
          zone_id: 1,
          recipe_revision_id: 7,
          plant_id: 2,
          planting_at: '2026-04-25T12:00:00Z',
        },
        errors: [],
        automationProfile: {
          assignments: { irrigation: 1, ph_correction: 2, ec_correction: 3 },
          waterForm: {},
          lightingForm: { enabled: false },
          zoneClimateForm: { enabled: false },
        } as never,
        ae3Online: true,
      },
    })
    const launchBtn = w.findAll('button').find((b) => b.text().includes('Запустить'))!
    expect(launchBtn.attributes('disabled')).toBeUndefined()
    await launchBtn.trigger('click')
    expect(w.emitted('launch')).toBeTruthy()
  })

  it('disables Запустить when readiness incomplete', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: { zone_id: 1 }, errors: [], ae3Online: false },
    })
    const launchBtn = w.findAll('button').find((b) => b.text().includes('Запустить'))!
    expect(launchBtn.attributes('disabled')).toBeDefined()
  })

  it('exposes diff-preview slot', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: {}, errors: [] },
      slots: { 'diff-preview': '<div data-test="diff">DIFF</div>' },
    })
    expect(w.find('[data-test="diff"]').exists()).toBe(true)
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

  it('formats planting_at as YYYY-MM-DD HH:MM', () => {
    const w = mount(PreviewStep, {
      props: {
        payloadPreview: { planting_at: '2026-04-25T08:30:00.000Z' },
        errors: [],
      },
    })
    expect(w.text()).toMatch(/2026-04-25 \d{2}:\d{2}/)
  })

  it('hint text mentions POST /grow-cycles endpoint', () => {
    const w = mount(PreviewStep, {
      props: { payloadPreview: {}, errors: [] },
    })
    expect(w.text()).toContain('/api/zones/{id}/grow-cycles')
  })
})
