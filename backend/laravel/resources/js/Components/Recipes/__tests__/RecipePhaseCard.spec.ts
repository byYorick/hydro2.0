import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RecipePhaseCard from '@/Components/Recipes/RecipePhaseCard.vue'
import { buildRecipePhaseVisuals } from '@/utils/recipeVisualization'

function makePhase(overrides: Record<string, unknown> = {}) {
  const [visual] = buildRecipePhaseVisuals([
    {
      id: 1,
      phase_index: 0,
      name: 'Проращивание',
      duration_hours: 96,
      ph_target: 5.8,
      ph_min: 5.6,
      ph_max: 6,
      ec_target: 0.8,
      temp_air_target: 25.5,
      humidity_target: 90,
      irrigation_mode: 'SUBSTRATE',
      irrigation_system_type: 'drip',
      irrigation_interval_sec: 900,
      irrigation_duration_sec: 20,
      lighting_photoperiod_hours: 18,
      lighting_start_time: '06:00:00',
      ...overrides,
    },
  ])

  return visual
}

describe('RecipePhaseCard.vue', () => {
  it('показывает номер, название и длительность фазы', () => {
    const wrapper = mount(RecipePhaseCard, { props: { phase: makePhase() } })

    expect(wrapper.text()).toContain('1. Проращивание')
    expect(wrapper.text()).toContain('4 дн')
    expect(wrapper.text()).toContain('дни 0–4')
  })

  it('показывает цель крупно, а коридор подписью', () => {
    const wrapper = mount(RecipePhaseCard, { props: { phase: makePhase() } })

    expect(wrapper.text()).toContain('5.8')
    expect(wrapper.text()).toContain('5.6–6')
  })

  it('подставляет диапазон вместо цели, когда target не задан', () => {
    const phase = makePhase({ ph_target: null })
    const wrapper = mount(RecipePhaseCard, { props: { phase } })

    expect(wrapper.text()).toContain('5.6–6')
  })

  it('расшифровывает режим и тип системы полива', () => {
    const wrapper = mount(RecipePhaseCard, { props: { phase: makePhase() } })

    expect(wrapper.text()).toContain('Пролив в субстрат')
    expect(wrapper.text()).toContain('Капельный')
    expect(wrapper.text()).toContain('Каждые 15 мин по 20 с')
  })

  it('рисует суточную полосу освещения', () => {
    const wrapper = mount(RecipePhaseCard, { props: { phase: makePhase() } })

    expect(wrapper.find('[data-testid="recipe-photoperiod-bar"]').exists()).toBe(true)
  })

  it('скрывает блок питания, если по фазе нет данных', () => {
    const wrapper = mount(RecipePhaseCard, { props: { phase: makePhase() } })

    expect(wrapper.find('[data-testid="recipe-nutrition-bar"]').exists()).toBe(false)
  })

  it('показывает блок питания при заданных долях', () => {
    const phase = makePhase({
      nutrient_npk_ratio_pct: 50,
      nutrient_calcium_ratio_pct: 50,
      nutrient_program_code: 'PROGRAM_V1',
    })
    const wrapper = mount(RecipePhaseCard, { props: { phase } })

    expect(wrapper.find('[data-testid="recipe-nutrition-bar"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Программа: PROGRAM_V1')
  })

  it('показывает чипы день/ночь при наличии профиля', () => {
    const phase = makePhase({
      day_night_enabled: true,
      extensions: { day_night: { temperature: { day: 26, night: 22 } } },
    })
    const wrapper = mount(RecipePhaseCard, { props: { phase } })

    expect(wrapper.text()).toContain('День / ночь')
    expect(wrapper.text()).toContain('T °C: 26 / 22')
  })
})
