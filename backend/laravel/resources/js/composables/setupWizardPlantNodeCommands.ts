import type { ComputedRef, Ref } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastVariant } from '@/composables/useToast'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'
import { extractSetupWizardErrorMessage } from './setupWizardErrors'
import type {
  Plant,
  SetupWizardDeviceAssignments,
  PlantFormState,
  SetupWizardLoadingState,
  Zone,
} from './setupWizardTypes'
import type { SetupWizardDataApiClient } from './setupWizardDataLoaders'

interface SetupWizardPlantNodeCommandsOptions {
  api: SetupWizardDataApiClient
  loading: SetupWizardLoadingState
  canConfigure: ComputedRef<boolean>
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  availablePlants: Ref<Plant[]>
  selectedPlantId: Ref<number | null>
  selectedZone: Ref<Zone | null>
  selectedPlant: Ref<Plant | null>
  selectedNodeIds: Ref<number[]>
  attachedNodesCount: Ref<number>
  plantForm: PlantFormState
  loaders: {
    loadPlants: () => Promise<void>
    loadAvailableNodes: () => Promise<void>
  }
}

export interface SetupWizardPlantNodeCommandActions {
  createPlant: () => Promise<void>
  selectPlant: () => void
  attachNodesToZone: (assignments?: SetupWizardDeviceAssignments | null) => Promise<void>
}

export function canSelectPlant(canConfigure: boolean, selectedPlantId: number | null): boolean {
  return canConfigure && selectedPlantId !== null
}

export function resolveSelectedPlant(plants: Plant[], selectedPlantId: number | null): Plant | null {
  if (!selectedPlantId) {
    return null
  }

  return plants.find((item) => item.id === selectedPlantId) ?? null
}

export function createSetupWizardPlantNodeCommands(
  options: SetupWizardPlantNodeCommandsOptions
): SetupWizardPlantNodeCommandActions {
  const {
    api,
    loading,
    canConfigure,
    showToast,
    availablePlants,
    selectedPlantId,
    selectedZone,
    selectedPlant,
    selectedNodeIds,
    attachedNodesCount,
    plantForm,
    loaders,
  } = options

  async function createPlant(): Promise<void> {
    if (!canConfigure.value || !plantForm.name.trim()) {
      return
    }

    loading.stepPlant = true
    try {
      const response = await api.post('/plants', {
        name: plantForm.name,
        species: plantForm.species || null,
        variety: plantForm.variety || null,
      })

      const payload = extractData<Record<string, unknown>>(response.data)
      const plantId = typeof payload?.id === 'number' ? payload.id : null
      if (!plantId) {
        throw new Error('Plant id missing in response')
      }

      selectedPlant.value = {
        id: plantId,
        name: plantForm.name,
      }
      selectedPlantId.value = plantId

      showToast('Растение создано', 'success', TOAST_TIMEOUT.NORMAL)
      await loaders.loadPlants()
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to create plant', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось создать растение'), 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      loading.stepPlant = false
    }
  }

  function selectPlant(): void {
    if (!canSelectPlant(canConfigure.value, selectedPlantId.value)) {
      return
    }

    const plant = resolveSelectedPlant(availablePlants.value, selectedPlantId.value)
    if (!plant) {
      return
    }

    selectedPlant.value = plant
    showToast('Растение выбрано', 'success', TOAST_TIMEOUT.NORMAL)
  }

  async function attachNodesToZone(assignments?: SetupWizardDeviceAssignments | null): Promise<void> {
    if (!canConfigure.value || !selectedZone.value?.id || selectedNodeIds.value.length === 0) {
      return
    }

    loading.stepDevices = true
    try {
      if (assignments) {
        await api.post('/setup-wizard/validate-devices', {
          zone_id: selectedZone.value.id,
          assignments,
          selected_node_ids: selectedNodeIds.value,
        })
      }

      await Promise.all(
        selectedNodeIds.value.map((nodeId) => api.patch(`/nodes/${nodeId}`, { zone_id: selectedZone.value?.id }))
      )

      if (assignments) {
        await api.post('/setup-wizard/apply-device-bindings', {
          zone_id: selectedZone.value.id,
          assignments,
          selected_node_ids: selectedNodeIds.value,
        })
      }

      attachedNodesCount.value = selectedNodeIds.value.length
      showToast(`Привязано узлов: ${attachedNodesCount.value}`, 'success', TOAST_TIMEOUT.NORMAL)

      selectedNodeIds.value = []
      await loaders.loadAvailableNodes()
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to attach nodes', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось привязать устройства к зоне'), 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      loading.stepDevices = false
    }
  }

  return {
    createPlant,
    selectPlant,
    attachNodesToZone,
  }
}
