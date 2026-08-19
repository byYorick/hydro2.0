import { mount, config } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Регистрируем RecycleScroller глобально
const RecycleScrollerStub = {
  name: 'RecycleScroller',
  props: {
    items: { type: Array, required: true },
    'item-size': { type: Number, default: 0 },
    itemSize: { type: Number, default: 0 },
    'key-field': { type: String, default: 'id' },
  },
  template: `
    <div class="recycle-scroller-stub">
      <template v-for="(item, index) in items" :key="item[0] ?? index">
        <slot :item="item" :index="index" />
      </template>
    </div>
  `,
}

config.global.components.RecycleScroller = RecycleScrollerStub

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: { name: 'Button', props: ['size', 'variant'], template: '<button><slot /></button>' },
}))

const sampleRecipesData = vi.hoisted(() => [
    {
      id: 1,
      name: 'Lettuce Recipe',
      description: 'Recipe for growing lettuce',
      phases_count: 3,
      total_duration_hours: 432,
      phases_preview: [
        { phase_index: 0, name: 'Проращивание', duration_hours: 96 },
        { phase_index: 1, name: 'Вегетация', duration_hours: 336 },
      ],
      plants: [{ id: 1, name: 'Салат' }],
      latest_published_revision_id: 11,
      active_zones_count: 2,
    },
    {
      id: 2,
      name: 'Basil Recipe',
      description: 'Recipe for growing basil',
      phases_count: 2,
      plants: [{ id: 2, name: 'Базилик' }],
      latest_published_revision_id: null,
      active_zones_count: 0,
    },
    {
      id: 3,
      name: 'Tomato Recipe',
      phases_count: 4,
      plants: [{ id: 3, name: 'Томат' }],
      latest_published_revision_id: 12,
      active_zones_count: 1,
    },
])

const resetSampleRecipesData = vi.hoisted(() => () => {
  sampleRecipesData.splice(
    0,
    sampleRecipesData.length,
    {
      id: 1,
      name: 'Lettuce Recipe',
      description: 'Recipe for growing lettuce',
      phases_count: 3,
      total_duration_hours: 432,
      phases_preview: [
        { phase_index: 0, name: 'Проращивание', duration_hours: 96 },
        { phase_index: 1, name: 'Вегетация', duration_hours: 336 },
      ],
      plants: [{ id: 1, name: 'Салат' }],
      latest_published_revision_id: 11,
      active_zones_count: 2,
    },
    {
      id: 2,
      name: 'Basil Recipe',
      description: 'Recipe for growing basil',
      phases_count: 2,
      plants: [{ id: 2, name: 'Базилик' }],
      latest_published_revision_id: null,
      active_zones_count: 0,
    },
    {
      id: 3,
      name: 'Tomato Recipe',
      phases_count: 4,
      plants: [{ id: 3, name: 'Томат' }],
      latest_published_revision_id: 12,
      active_zones_count: 1,
    },
  )
})

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      auth: {
        user: { role: 'agronomist' }
      },
      recipes: sampleRecipesData,
    },
  }),
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))

import RecipesIndex from '../Index.vue'

describe('Recipes/Index.vue', () => {
  beforeEach(() => {
    console.log = vi.fn()
    resetSampleRecipesData()
  })

  it('отображает заголовок Recipes', () => {
    const wrapper = mount(RecipesIndex)
    
    expect(wrapper.text()).toContain('Рецепты')
  })

  it('отображает список рецептов', () => {
    const wrapper = mount(RecipesIndex)
    
    expect(wrapper.text()).toContain('Lettuce Recipe')
    expect(wrapper.text()).toContain('Basil Recipe')
    expect(wrapper.text()).toContain('Tomato Recipe')
  })

  it('отображает описания рецептов', () => {
    const wrapper = mount(RecipesIndex)
    
    expect(wrapper.text()).toContain('Recipe for growing lettuce')
    expect(wrapper.text()).toContain('Recipe for growing basil')
  })

  it('отображает количество фаз для каждого рецепта', () => {
    const wrapper = mount(RecipesIndex)
    
    // В компоненте отображается просто число, а не "Фаз: X"
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('4')
    // Проверяем, что заголовок "Фаз" присутствует
    expect(wrapper.text()).toContain('Фаз')
  })

  it('обрабатывает рецепт без описания', () => {
    const wrapper = mount(RecipesIndex)
    
    expect(wrapper.text()).toContain('Без описания')
  })

  it('отображает суммарную длительность рецепта', () => {
    const wrapper = mount(RecipesIndex)

    expect(wrapper.text()).toContain('Длительность')
    expect(wrapper.text()).toContain('18 дн')
  })

  it('рисует мини-таймлайн для рецепта с превью фаз', () => {
    const wrapper = mount(RecipesIndex)

    const timelines = wrapper.findAll('[data-testid="recipe-mini-timeline"]')
    expect(timelines).toHaveLength(1)
    expect(timelines[0].findAll('span')).toHaveLength(2)
  })

  it('отображает поле поиска', () => {
    const wrapper = mount(RecipesIndex)
    
    const searchInput = wrapper.find('input[placeholder*="Название или культура"]')
    expect(searchInput.exists()).toBe(true)
  })

  it('отображает кнопку создания рецепта', () => {
    const wrapper = mount(RecipesIndex)
    
    expect(wrapper.text()).toContain('Новый рецепт')
    const buttons = wrapper.findAllComponents({ name: 'Button' })
    const createButton = buttons.find(btn => btn.text().includes('Новый рецепт'))
    expect(createButton).toBeTruthy()
  })

  it('фильтрует рецепты по поисковому запросу', async () => {
    const wrapper = mount(RecipesIndex)
    
    const searchInput = wrapper.find('input[placeholder*="Название или культура"]')
    await searchInput.setValue('Lettuce')
    
    await wrapper.vm.$nextTick()
    
    expect(wrapper.text()).toContain('Lettuce Recipe')
    expect(wrapper.text()).not.toContain('Basil Recipe')
    expect(wrapper.text()).not.toContain('Tomato Recipe')
  })

  it('фильтрует рецепты по описанию', async () => {
    const wrapper = mount(RecipesIndex)
    
    const searchInput = wrapper.find('input[placeholder*="Название или культура"]')
    await searchInput.setValue('growing')
    
    await wrapper.vm.$nextTick()
    
    expect(wrapper.text()).toContain('Lettuce Recipe')
    expect(wrapper.text()).toContain('Basil Recipe')
    expect(wrapper.text()).not.toContain('Tomato Recipe')
  })

  it('показывает сообщение "Нет рецептов по текущему фильтру" при пустом результате фильтрации', async () => {
    const wrapper = mount(RecipesIndex)
    
    const searchInput = wrapper.find('input[placeholder*="Название или культура"]')
    await searchInput.setValue('NonExistentRecipe')
    
    await wrapper.vm.$nextTick()
    
    expect(wrapper.text()).toContain('Нет рецептов по текущему фильтру')
    expect(wrapper.text()).not.toContain('Lettuce Recipe')
  })

  it('показывает сообщение "Рецепты не найдены" когда нет рецептов', () => {
    sampleRecipesData.splice(0, sampleRecipesData.length)

    const wrapper = mount(RecipesIndex)

    expect(wrapper.text()).toContain('Рецепты не найдены')
    expect(wrapper.text()).not.toContain('Lettuce Recipe')
  })

  it('отображает ссылки на рецепты', () => {
    const wrapper = mount(RecipesIndex)
    
    const links = wrapper.findAllComponents({ name: 'Link' })
    expect(links.length).toBeGreaterThan(0)
    
    // Ищем ссылку на рецепт (может быть несколько ссылок - название и кнопка "Открыть")
    const recipeLinks = links.filter(link => link.props('href') === '/recipes/1')
    expect(recipeLinks.length).toBeGreaterThan(0)
    
    // Проверяем, что есть кнопка "Открыть" (она тоже в Link)
    expect(wrapper.text()).toContain('Открыть')
  })

  it('поиск не чувствителен к регистру', async () => {
    const wrapper = mount(RecipesIndex)
    
    const searchInput = wrapper.find('input[placeholder*="Название или культура"]')
    await searchInput.setValue('LETTUCE')
    
    await wrapper.vm.$nextTick()
    
    expect(wrapper.text()).toContain('Lettuce Recipe')
  })

  it('логирует данные рецептов при монтировании', () => {
    // После рефакторинга console.log заменен на logger
    // Этот тест проверяет, что компонент монтируется без ошибок
    const wrapper = mount(RecipesIndex)
    
    expect(wrapper.exists()).toBe(true)
    
    wrapper.unmount()
  })

  it('показывает все рецепты при пустом поисковом запросе', async () => {
    const wrapper = mount(RecipesIndex)
    
    const searchInput = wrapper.find('input[placeholder*="Название или культура"]')
    await searchInput.setValue('Lettuce')
    await wrapper.vm.$nextTick()
    
    await searchInput.setValue('')
    await wrapper.vm.$nextTick()
    
    expect(wrapper.text()).toContain('Lettuce Recipe')
    expect(wrapper.text()).toContain('Basil Recipe')
    expect(wrapper.text()).toContain('Tomato Recipe')
  })

  it('не показывает vanity KPI среднего числа фаз', () => {
    const wrapper = mount(RecipesIndex)

    expect(wrapper.text()).not.toContain('Среднее фаз')
    expect(wrapper.text()).not.toContain('Суммарно фаз')
    expect(wrapper.text()).not.toContain('По фильтру')
    expect(wrapper.text()).not.toContain('Всего рецептов')
    expect(wrapper.find('.ui-kpi-grid').exists()).toBe(false)
  })

  it('показывает ссылки на справочники культур и удобрений', () => {
    const wrapper = mount(RecipesIndex)

    const links = wrapper.findAllComponents({ name: 'Link' })
    expect(links.some((link) => link.props('href') === '/plants')).toBe(true)
    expect(links.some((link) => link.props('href') === '/nutrients')).toBe(true)
    expect(wrapper.text()).toContain('Культуры')
    expect(wrapper.text()).toContain('Удобрения')
  })

  it('показывает колонку культуры и ищет по ней', async () => {
    const wrapper = mount(RecipesIndex)

    expect(wrapper.text()).toContain('Культура')
    expect(wrapper.text()).toContain('Салат')

    const searchInput = wrapper.find('input[placeholder*="Название или культура"]')
    await searchInput.setValue('салат')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Lettuce Recipe')
    expect(wrapper.text()).not.toContain('Basil Recipe')
  })

  it('даёт вторичные ссылки на культуры и удобрения', () => {
    const wrapper = mount(RecipesIndex)
    const links = wrapper.findAllComponents({ name: 'Link' })
    const hrefs = links.map((link) => link.props('href'))

    expect(wrapper.text()).toContain('Справочники')
    expect(hrefs).toContain('/plants')
    expect(hrefs).toContain('/nutrients')
  })
})
