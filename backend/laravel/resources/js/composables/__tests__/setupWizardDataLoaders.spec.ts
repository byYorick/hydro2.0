import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { createSetupWizardDataLoaders } from '@/composables/setupWizardDataLoaders'
import type { SetupWizardLoadingState } from '@/composables/setupWizardTypes'

function createLoadingState(): SetupWizardLoadingState {
  return {
    greenhouses: false,
    zones: false,
    plants: false,
    recipes: false,
    nodes: false,
    stepGreenhouse: false,
    stepZone: false,
    stepPlant: false,
    stepRecipe: false,
    stepDevices: false,
    stepAutomation: false,
    stepLaunch: false,
  }
}

describe('setupWizardDataLoaders', () => {
  it('показывает toast и очищает список теплиц при ошибке загрузки', async () => {
    const showToast = vi.fn()
    const availableGreenhouses = ref([{ id: 1, name: 'GH stale' }])

    const loaders = createSetupWizardDataLoaders({
      api: {
        get: vi.fn().mockRejectedValue({
          response: { data: { message: 'Boom greenhouses' } },
        }),
        post: vi.fn(),
        patch: vi.fn(),
      },
      loading: createLoadingState(),
      showToast,
      availableGreenhouses,
      availableGreenhouseTypes: ref([]),
      availableZones: ref([]),
      availablePlants: ref([]),
      availableRecipes: ref([]),
      availableNodes: ref([]),
      selectedGreenhouse: ref(null),
    })

    await loaders.loadGreenhouses()

    expect(availableGreenhouses.value).toEqual([])
    expect(showToast).toHaveBeenCalled()
    expect(showToast.mock.calls[0]?.[0]).toBe('Boom greenhouses')
  })

  it('не делает запрос зон без выбранной теплицы', async () => {
    const showToast = vi.fn()
    const apiGet = vi.fn()

    const loaders = createSetupWizardDataLoaders({
      api: {
        get: apiGet,
        post: vi.fn(),
        patch: vi.fn(),
      },
      loading: createLoadingState(),
      showToast,
      availableGreenhouses: ref([]),
      availableGreenhouseTypes: ref([]),
      availableZones: ref([]),
      availablePlants: ref([]),
      availableRecipes: ref([]),
      availableNodes: ref([]),
      selectedGreenhouse: ref(null),
    })

    await loaders.loadZones()

    expect(apiGet).not.toHaveBeenCalled()
    expect(showToast).not.toHaveBeenCalled()
  })
})
