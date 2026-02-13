import type { Ref } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastVariant } from '@/composables/useToast'
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
import { extractSetupWizardErrorMessage } from './setupWizardErrors'

export interface SetupWizardDataApiClient {
  get(url: string, config?: unknown): Promise<{ data: unknown }>
  post(url: string, data?: unknown, config?: unknown): Promise<{ data: unknown }>
  patch(url: string, data?: unknown, config?: unknown): Promise<{ data: unknown }>
}

interface SetupWizardDataLoadersOptions {
  api: SetupWizardDataApiClient
  loading: SetupWizardLoadingState
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
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
    showToast,
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
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить типы теплиц'), 'error', TOAST_TIMEOUT.NORMAL)
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
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить список теплиц'), 'error', TOAST_TIMEOUT.NORMAL)
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
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить список зон'), 'error', TOAST_TIMEOUT.NORMAL)
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
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить список растений'), 'error', TOAST_TIMEOUT.NORMAL)
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
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить список рецептов'), 'error', TOAST_TIMEOUT.NORMAL)
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
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить список узлов'), 'error', TOAST_TIMEOUT.NORMAL)
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
