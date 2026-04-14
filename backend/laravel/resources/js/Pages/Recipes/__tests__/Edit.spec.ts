import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const plantsListMock = vi.hoisted(() => vi.fn())
const nutrientProductsListMock = vi.hoisted(() => vi.fn())
const recipesGetByIdMock = vi.hoisted(() => vi.fn())
const recipesCreateMock = vi.hoisted(() => vi.fn())
const recipesUpdateMock = vi.hoisted(() => vi.fn())
const recipesCreateRevisionMock = vi.hoisted(() => vi.fn())
const recipesPublishRevisionMock = vi.hoisted(() => vi.fn())
const recipesCreatePhaseMock = vi.hoisted(() => vi.fn())
const recipesUpdatePhaseMock = vi.hoisted(() => vi.fn())
const recipesDeletePhaseMock = vi.hoisted(() => vi.fn())
const routerVisitMock = vi.hoisted(() => vi.fn())
const showToastMock = vi.hoisted(() => vi.fn())

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'size', 'variant'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/services/api', () => ({
  api: {
    plants: {
      list: plantsListMock,
    },
    nutrientProducts: {
      list: nutrientProductsListMock,
    },
    recipes: {
      getById: recipesGetByIdMock,
      create: recipesCreateMock,
      update: recipesUpdateMock,
      createRevision: recipesCreateRevisionMock,
      publishRevision: recipesPublishRevisionMock,
      createPhase: recipesCreatePhaseMock,
      updatePhase: recipesUpdatePhaseMock,
      deletePhase: recipesDeletePhaseMock,
    },
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: showToastMock,
  }),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

const usePageMock = vi.hoisted(() => vi.fn())

vi.mock('@inertiajs/vue3', () => ({
  usePage: usePageMock,
  router: {
    visit: routerVisitMock,
  },
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))

import RecipesEdit from '../Edit.vue'

const sampleRecipe = {
  id: 1,
  draft_revision_id: 20,
  latest_published_revision_id: 10,
  name: 'Test Recipe',
  description: 'Test Description',
  plants: [{ id: 1, name: 'Test Plant' }],
  phases: [
    {
      id: 101,
      phase_index: 0,
      name: 'Seedling',
      duration_hours: 168,
      ph_target: 5.8,
      ph_min: 5.6,
      ph_max: 6.0,
      ec_target: 1.4,
      ec_min: 1.2,
      ec_max: 1.6,
      temp_air_target: 23,
      humidity_target: 62,
      lighting_photoperiod_hours: 16,
      lighting_start_time: '06:00:00',
      irrigation_mode: 'SUBSTRATE',
      irrigation_interval_sec: 900,
      irrigation_duration_sec: 15,
      nutrient_program_code: 'YARAREGA_CALCINIT_HAIFA_MICRO_V1',
      nutrient_npk_ratio_pct: 44,
      nutrient_calcium_ratio_pct: 36,
      nutrient_magnesium_ratio_pct: 17,
      nutrient_micro_ratio_pct: 3,
      targets: {
        ph: { min: 5.6, max: 6.0 },
        ec: { min: 1.2, max: 1.6 },
      },
      extensions: {
        day_night: {
          ph: { day: 5.8, night: 5.7 },
          ec: { day: 1.5, night: 1.4 },
          temperature: { day: 23, night: 20 },
          humidity: { day: 62, night: 66 },
          lighting: { day_start_time: '06:00:00', day_hours: 16 },
        },
        subsystems: {
          irrigation: {
            targets: {
              system_type: 'drip',
            },
          },
        },
      },
    },
  ],
}

describe('Recipes/Edit.vue', () => {
  beforeEach(() => {
    plantsListMock.mockReset()
    nutrientProductsListMock.mockReset()
    recipesGetByIdMock.mockReset()
    recipesCreateMock.mockReset()
    recipesUpdateMock.mockReset()
    recipesCreateRevisionMock.mockReset()
    recipesPublishRevisionMock.mockReset()
    recipesCreatePhaseMock.mockReset()
    recipesUpdatePhaseMock.mockReset()
    recipesDeletePhaseMock.mockReset()
    routerVisitMock.mockReset()
    showToastMock.mockReset()

    usePageMock.mockReturnValue({
      props: {
        recipe: sampleRecipe,
      },
    })

    plantsListMock.mockResolvedValue([{ id: 1, name: 'Test Plant' }])
    nutrientProductsListMock.mockResolvedValue([
      { id: 1, manufacturer: 'Yara', name: 'Grow', component: 'npk' },
      { id: 2, manufacturer: 'Yara', name: 'Calcinit', component: 'calcium' },
      { id: 3, manufacturer: 'TerraTarsa', name: 'Mg', component: 'magnesium' },
      { id: 4, manufacturer: 'Haifa', name: 'Micro', component: 'micro' },
    ])
    recipesGetByIdMock.mockResolvedValue(sampleRecipe)
    recipesUpdateMock.mockResolvedValue(undefined)
    recipesUpdatePhaseMock.mockResolvedValue(undefined)
    recipesDeletePhaseMock.mockResolvedValue(undefined)
    recipesCreatePhaseMock.mockResolvedValue({ id: 101 })
    recipesPublishRevisionMock.mockResolvedValue(undefined)
  })

  it('рендерит recipe через shared editor', async () => {
    const wrapper = mount(RecipesEdit)
    await flushPromises()

    expect(wrapper.text()).toContain('Редактировать рецепт')
    // recipe-name-display — композитный title "Plant — Label".
    expect(wrapper.get('[data-testid="recipe-name-display"]').text()).toContain('Test Plant')
    expect(wrapper.get('[data-testid="recipe-name-display"]').text()).toContain('Test Description')
    expect(wrapper.find('[data-testid="phase-item-0"]').exists()).toBe(true)
  })

  it('позволяет добавить фазу', async () => {
    const wrapper = mount(RecipesEdit)
    await flushPromises()

    await wrapper.get('[data-testid="add-phase-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="phase-item-1"]').exists()).toBe(true)
  })

  it('сохраняет рецепт и публикует ревизию единым editor flow', async () => {
    const wrapper = mount(RecipesEdit)
    await flushPromises()

    await wrapper.get('[data-testid="save-recipe-button"]').trigger('click')
    await flushPromises()

    // UI composes recipe name from plant + description для новой модели ("Plant — Label"),
    // см. RecipeEditor.vue recipeName computed.
    expect(recipesUpdateMock).toHaveBeenCalledWith(1, expect.objectContaining({
      plant_id: 1,
    }))
    expect(recipesUpdatePhaseMock).toHaveBeenCalledWith(101, expect.objectContaining({
      phase_index: 0,
      name: 'Seedling',
      ph_target: 5.8,
      ec_target: 1.4,
      extensions: expect.objectContaining({
        day_night: expect.any(Object),
        subsystems: expect.objectContaining({
          irrigation: expect.objectContaining({
            targets: expect.objectContaining({
              system_type: 'drip',
            }),
          }),
        }),
      }),
    }))
    expect(recipesPublishRevisionMock).toHaveBeenCalledWith(20)
    expect(routerVisitMock).toHaveBeenCalledWith('/recipes/1')
  })

  it('для published recipe создаёт draft clone и не patch-ит published phase ids', async () => {
    usePageMock.mockReturnValue({
      props: {
        recipe: {
          ...sampleRecipe,
          draft_revision_id: null,
          latest_draft_revision_id: null,
        },
      },
    })

    recipesCreateRevisionMock.mockResolvedValue({
      id: 30,
      phases: [
        { id: 301, phase_index: 0, name: 'Seedling' },
      ],
    })
    recipesCreatePhaseMock.mockResolvedValue({ id: 401 })

    const wrapper = mount(RecipesEdit)
    await flushPromises()

    await wrapper.get('[data-testid="save-recipe-button"]').trigger('click')
    await flushPromises()

    expect(recipesCreateRevisionMock).toHaveBeenCalledWith(1, expect.objectContaining({
      clone_from_revision_id: 10,
    }))
    expect(recipesDeletePhaseMock).toHaveBeenCalledWith(301)
    expect(recipesCreatePhaseMock).toHaveBeenCalledWith(30, expect.objectContaining({
      phase_index: 0,
      name: 'Seedling',
      ph_target: 5.8,
    }))
    expect(recipesUpdatePhaseMock).not.toHaveBeenCalledWith(101, expect.anything())
    expect(recipesPublishRevisionMock).toHaveBeenCalledWith(30)
  })
})
