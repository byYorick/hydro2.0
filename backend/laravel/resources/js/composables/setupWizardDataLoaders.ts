import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import type {
  Greenhouse,
  GreenhouseType,
  Node,
  Plant,
  Recipe,
  SetupWizardLoadingState,
  Zone,
} from './setupWizardTypes'
import { extractCollection } from './setupWizardCollection'

export interface SetupWizardDataApiClient {
  get(url: string, config?: unknown): Promise<{ data: unknown }>
  post(url: string, data?: unknown, config?: unknown): Promise<{ data: unknown }>
  patch(url: string, data?: unknown, config?: unknown): Promise<{ data: unknown }>
}

interface SetupWizardDataLoadersOptions {
  api: SetupWizardDataApiClient
  loading: SetupWizardLoadingState
  availableGreenhouses: Ref<Greenhouse[]>
  availableGreenhouseTypes: Ref<GreenhouseType[]>
  availableZones: Ref<Zone[]>
  availablePlants: Ref<Plant[]>
  availableRecipes: Ref<Recipe[]>
  availableNodes: Ref<Node[]>
  selectedGreenhouse: Ref<Greenhouse | null>
}

export interface SetupWizardDataLoaderActions {
  loadGreenhouseTypes: () => Promise<void>
  loadGreenhouses: () => Promise<void>
  loadZones: (greenhouseId?: number) => Promise<void>
  loadPlants: () => Promise<void>
  loadRecipes: () => Promise<void>
  loadAvailableNodes: () => Promise<void>
}

export function createSetupWizardDataLoaders(options: SetupWizardDataLoadersOptions): SetupWizardDataLoaderActions {
  const {
    api,
    loading,
    availableGreenhouses,
    availableGreenhouseTypes,
    availableZones,
    availablePlants,
    availableRecipes,
    availableNodes,
    selectedGreenhouse,
  } = options

  async function loadGreenhouseTypes(): Promise<void> {
    try {
      const response = await api.get('/greenhouse-types')
      availableGreenhouseTypes.value = extractCollection<GreenhouseType>(response.data)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load greenhouse types', { error })
      availableGreenhouseTypes.value = []
    }
  }

  async function loadGreenhouses(): Promise<void> {
    loading.greenhouses = true
    try {
      const response = await api.get('/greenhouses')
      availableGreenhouses.value = extractCollection<Greenhouse>(response.data)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load greenhouses', { error })
      availableGreenhouses.value = []
    } finally {
      loading.greenhouses = false
    }
  }

  async function loadZones(greenhouseId?: number): Promise<void> {
    const targetGreenhouseId = greenhouseId ?? selectedGreenhouse.value?.id
    if (!targetGreenhouseId) {
      return
    }

    loading.zones = true
    try {
      const response = await api.get('/zones', {
        params: { greenhouse_id: targetGreenhouseId },
      })

      availableZones.value = extractCollection<Zone>(response.data)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load zones', { error })
      availableZones.value = []
    } finally {
      loading.zones = false
    }
  }

  async function loadPlants(): Promise<void> {
    loading.plants = true
    try {
      const response = await api.get('/plants')
      availablePlants.value = extractCollection<Plant>(response.data)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load plants', { error })
      availablePlants.value = []
    } finally {
      loading.plants = false
    }
  }

  async function loadRecipes(): Promise<void> {
    loading.recipes = true
    try {
      const response = await api.get('/recipes')
      availableRecipes.value = extractCollection<Recipe>(response.data)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load recipes', { error })
      availableRecipes.value = []
    } finally {
      loading.recipes = false
    }
  }

  async function loadAvailableNodes(): Promise<void> {
    loading.nodes = true
    try {
      const response = await api.get('/nodes', {
        params: { unassigned: true },
      })

      availableNodes.value = extractCollection<Node>(response.data)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load nodes', { error })
      availableNodes.value = []
    } finally {
      loading.nodes = false
    }
  }

  return {
    loadGreenhouseTypes,
    loadGreenhouses,
    loadZones,
    loadPlants,
    loadRecipes,
    loadAvailableNodes,
  }
}
