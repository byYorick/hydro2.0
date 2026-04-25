import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({
  api: {
    plants: {
      create: vi.fn(),
    },
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}))

import {
  _resetLaunchPreferencesForTests,
} from '@/composables/useLaunchPreferences'
import RecipeStep from '../RecipeStep.vue'

const plants = [
  { id: 1, name: 'Tomato' },
  { id: 2, name: 'Lettuce' },
]
const recipes = [
  {
    id: 11,
    name: 'Tomato NFT',
    latest_published_revision_id: 3,
    plants: [{ id: 1, name: 'Tomato' }],
  },
  {
    id: 12,
    name: 'Tomato Drip Draft',
    latest_published_revision_id: null,
    plants: [{ id: 1, name: 'Tomato' }],
  },
  {
    id: 13,
    name: 'Lettuce Butterhead',
    latest_published_revision_id: 1,
    plants: [{ id: 2, name: 'Lettuce' }],
  },
]

describe('RecipeStep', () => {
  beforeEach(() => {
    localStorage.clear()
    _resetLaunchPreferencesForTests()
  })

  it('renders Растение card with plant select', () => {
    const w = mount(RecipeStep, { props: { plants, recipes } })
    expect(w.text()).toContain('Растение')
    const select = w.find('select')
    expect(select.exists()).toBe(true)
    expect(select.html()).toContain('Tomato')
    expect(select.html()).toContain('Lettuce')
  })

  it('hides Рецепт card until plant is selected', () => {
    const w = mount(RecipeStep, { props: { plants, recipes } })
    expect(w.text()).not.toContain('Рецепт и ревизия')
  })

  it('shows Рецепт card with filtered recipes once plant is set', () => {
    const w = mount(RecipeStep, { props: { plants, recipes, plantId: 1 } })
    expect(w.text()).toContain('Рецепт и ревизия')
    expect(w.text()).toContain('Tomato NFT')
    expect(w.text()).not.toContain('Lettuce Butterhead')
  })

  it('emits update:recipeRevisionId with latest_published_revision_id on recipe pick', async () => {
    const w = mount(RecipeStep, { props: { plants, recipes, plantId: 1 } })
    // Recipe select is the 2nd <select> on the page (1st is plant)
    const selects = w.findAll('select')
    expect(selects.length).toBeGreaterThanOrEqual(2)
    await selects[1].setValue('11')
    expect(w.emitted('update:recipeRevisionId')).toBeTruthy()
    expect(w.emitted('update:recipeRevisionId')![0]).toEqual([3])
  })

  it('emits undefined revision when recipe has no published revision', async () => {
    const w = mount(RecipeStep, { props: { plants, recipes, plantId: 1 } })
    const selects = w.findAll('select')
    await selects[1].setValue('12')
    expect(w.emitted('update:recipeRevisionId')![0]).toEqual([undefined])
  })

  it('reveals Дата и партия card after recipe selected', async () => {
    const w = mount(RecipeStep, { props: { plants, recipes, plantId: 1 } })
    expect(w.text()).not.toContain('Дата и время посадки')
    await w.findAll('select')[1].setValue('11')
    await flushPromises()
    expect(w.text()).toContain('Дата и время посадки')
  })
})
