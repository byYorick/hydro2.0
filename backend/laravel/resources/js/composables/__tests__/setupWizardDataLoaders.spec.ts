import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const greenhousesListMock = vi.hoisted(() => vi.fn())
const zonesListMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    greenhouses: {
      list: greenhousesListMock,
      types: vi.fn().mockResolvedValue([]),
    },
    zones: {
      list: zonesListMock,
    },
    plants: {
      list: vi.fn().mockResolvedValue([]),
    },
    recipes: {
      list: vi.fn().mockResolvedValue([]),
    },
    nodes: {
      list: vi.fn().mockResolvedValue([]),
    },
  },
}))

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

    greenhousesListMock.mockRejectedValueOnce({
      response: { data: { message: 'Boom greenhouses' } },
    })

    const loaders = createSetupWizardDataLoaders({
      loading: createLoadingState(),
      showToast,
      availableGreenhouses,
      availableGreenhouseTypes: ref([]),
      availableZones: ref([]),
      availablePlants: ref([]),
      availableRecipes: ref([]),
      availableNodes: ref([]),
      greenhouseClimateNodes: ref([]),
      selectedGreenhouse: ref(null),
      selectedZone: ref(null),
      selectedZoneId: ref(null),
    })

    await loaders.loadGreenhouses()

    expect(availableGreenhouses.value).toEqual([])
    expect(showToast).toHaveBeenCalled()
    expect(showToast.mock.calls[0]?.[0]).toBe('Произошла ошибка сервиса. Проверьте логи и повторите попытку.')
  })

  it('не делает запрос зон без выбранной теплицы', async () => {
    const showToast = vi.fn()
    zonesListMock.mockReset()

    const loaders = createSetupWizardDataLoaders({
      loading: createLoadingState(),
      showToast,
      availableGreenhouses: ref([]),
      availableGreenhouseTypes: ref([]),
      availableZones: ref([]),
      availablePlants: ref([]),
      availableRecipes: ref([]),
      availableNodes: ref([]),
      greenhouseClimateNodes: ref([]),
      selectedGreenhouse: ref(null),
      selectedZone: ref(null),
      selectedZoneId: ref(null),
    })

    await loaders.loadZones()

    expect(zonesListMock).not.toHaveBeenCalled()
    expect(showToast).not.toHaveBeenCalled()
  })
})
