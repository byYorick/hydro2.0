import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RecipeParameterChart from '@/Components/Recipes/RecipeParameterChart.vue'
import { buildRecipePhaseVisuals } from '@/utils/recipeVisualization'

const phases = buildRecipePhaseVisuals([
  {
    id: 1,
    phase_index: 0,
    name: 'Проращивание',
    duration_hours: 96,
    ph_target: 5.8,
    ph_min: 5.6,
    ph_max: 6,
  },
  {
    id: 2,
    phase_index: 1,
    name: 'Вегетация',
    duration_hours: 288,
    ph_target: 6.1,
    ph_min: 5.9,
    ph_max: 6.3,
  },
])

describe('RecipeParameterChart.vue', () => {
  it('рисует коридор min–max для каждой фазы', () => {
    const wrapper = mount(RecipeParameterChart, { props: { phases, metric: 'ph' } })

    expect(wrapper.findAll('rect')).toHaveLength(2)
  })

  it('строит ступенчатую линию целей по двум точкам на фазу', () => {
    const wrapper = mount(RecipeParameterChart, { props: { phases, metric: 'ph' } })

    const points = wrapper.find('polyline').attributes('points')?.split(' ') ?? []
    expect(points).toHaveLength(4)
  })

  it('подписывает график названием метрики', () => {
    const wrapper = mount(RecipeParameterChart, { props: { phases, metric: 'ph' } })

    expect(wrapper.text()).toContain('pH раствора')
  })

  it('показывает заглушку, если по метрике нет данных', () => {
    const wrapper = mount(RecipeParameterChart, { props: { phases, metric: 'co2' } })

    expect(wrapper.find('svg').exists()).toBe(false)
    expect(wrapper.text()).toContain('Нет данных по параметру')
  })
})
