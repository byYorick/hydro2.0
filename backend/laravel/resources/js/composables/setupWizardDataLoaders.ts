import type { Ref } from 'vue'
import { api } from '@/services/api'
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

interface SetupWizardDataLoadersOptions {
  loading: SetupWizardLoadingState
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  availableGreenhouses: Ref<Greenhouse[]>
  availableGreenhouseTypes: Ref<GreenhouseType[]>
  availableZones: Ref<Zone[]>
  availablePlants: Ref<Plant[]>
  availableRecipes: Ref<Recipe[]>
  availableNodes: Ref<Node[]>
  greenhouseClimateNodes: Ref<Node[]>
  selectedGreenhouse: Ref<Greenhouse | null>
  selectedZone: Ref<Zone | null>
  selectedZoneId: Ref<number | null>
}

interface SetupWizardNodeLoadOptions {
  greenhouseId?: number | null
  includeUnassigned?: boolean
}

export interface SetupWizardDataLoaderActions {
  loadGreenhouseTypes: () => Promise<void>
  loadGreenhouses: () => Promise<void>
  loadZones: (greenhouseId?: number) => Promise<void>
  loadPlants: () => Promise<void>
  loadRecipes: () => Promise<void>
  loadAvailableNodes: () => Promise<void>
  loadGreenhouseClimateNodes: (options?: SetupWizardNodeLoadOptions) => Promise<void>
}

export function createSetupWizardDataLoaders(options: SetupWizardDataLoadersOptions): SetupWizardDataLoaderActions {
  const {
    loading,
    showToast,
    availableGreenhouses,
    availableGreenhouseTypes,
    availableZones,
    availablePlants,
    availableRecipes,
    availableNodes,
    greenhouseClimateNodes,
    selectedGreenhouse,
    selectedZone,
    selectedZoneId,
  } = options

  async function loadGreenhouseTypes(): Promise<void> {
    try {
      const types = await api.greenhouses.types()
      availableGreenhouseTypes.value = extractCollection<GreenhouseType>(types)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load greenhouse types', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить типы теплиц'), 'error', TOAST_TIMEOUT.NORMAL)
      availableGreenhouseTypes.value = []
    }
  }

  async function loadGreenhouses(): Promise<void> {
    loading.greenhouses = true
    try {
      const greenhouses = await api.greenhouses.list()
      availableGreenhouses.value = extractCollection<Greenhouse>(greenhouses)
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
      const zones = await api.zones.list({ greenhouse_id: targetGreenhouseId })
      availableZones.value = extractCollection<Zone>(zones)
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
      const plants = await api.plants.list()
      availablePlants.value = extractCollection<Plant>(plants)
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
      const recipes = await api.recipes.list()
      availableRecipes.value = extractCollection<Recipe>(recipes)
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
      const zoneId = selectedZone.value?.id ?? selectedZoneId.value ?? null
      const nodes = await api.nodes.list(
        zoneId
          ? { zone_id: zoneId, include_unassigned: true }
          : { unassigned: true },
      )
      availableNodes.value = extractCollection<Node>(nodes)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load nodes', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить список узлов'), 'error', TOAST_TIMEOUT.NORMAL)
      availableNodes.value = []
    } finally {
      loading.nodes = false
    }
  }

  async function loadGreenhouseClimateNodes(options?: SetupWizardNodeLoadOptions): Promise<void> {
    const greenhouseId = options?.greenhouseId ?? selectedGreenhouse.value?.id ?? null
    if (!greenhouseId) {
      greenhouseClimateNodes.value = []
      return
    }

    loading.nodes = true
    try {
      const nodes = await api.nodes.list({
        greenhouse_id: greenhouseId,
        include_unassigned: options?.includeUnassigned ?? true,
      })
      greenhouseClimateNodes.value = extractCollection<Node>(nodes)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to load greenhouse climate nodes', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось загрузить greenhouse climate узлы'), 'error', TOAST_TIMEOUT.NORMAL)
      greenhouseClimateNodes.value = []
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
    loadGreenhouseClimateNodes,
  }
}
