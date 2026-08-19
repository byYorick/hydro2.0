import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RecipePhaseTimeline from '@/Components/Recipes/RecipePhaseTimeline.vue'
import { buildRecipePhaseVisuals } from '@/utils/recipeVisualization'

const phases = buildRecipePhaseVisuals([
  { id: 1, phase_index: 0, name: 'Проращивание', duration_hours: 96 },
  { id: 2, phase_index: 1, name: 'Вегетация', duration_hours: 288 },
])

describe('RecipePhaseTimeline.vue', () => {
  it('рисует сегмент на каждую фазу', () => {
    const wrapper = mount(RecipePhaseTimeline, { props: { phases } })

    expect(wrapper.findAll('button')).toHaveLength(2)
  })

  it('задаёт ширину сегмента пропорционально длительности фазы', () => {
    const wrapper = mount(RecipePhaseTimeline, { props: { phases } })

    const [first, second] = wrapper.findAll('button')
    expect(first.attributes('style')).toContain('width: 25%')
    expect(second.attributes('style')).toContain('width: 75%')
  })

  it('показывает суммарную длительность цикла', () => {
    const wrapper = mount(RecipePhaseTimeline, { props: { phases } })

    expect(wrapper.text()).toContain('16 дн')
  })

  it('эмитит выбор фазы по клику', async () => {
    const wrapper = mount(RecipePhaseTimeline, { props: { phases } })

    await wrapper.findAll('button')[1].trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual(['2'])
  })

  it('предупреждает, если у фазы не задана длительность', () => {
    const wrapper = mount(RecipePhaseTimeline, {
      props: { phases: buildRecipePhaseVisuals([{ id: 1, phase_index: 0, name: 'Без срока' }]) },
    })

    expect(wrapper.text()).toContain('У части фаз не задана длительность')
  })
})
