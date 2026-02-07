import type { ComputedRef, Ref } from 'vue'
import type { ToastVariant } from '@/composables/useToast'
import type {
  Greenhouse,
  GreenhouseFormState,
  Plant,
  PlantFormState,
  SetupWizardLoadingState,
  Zone,
  ZoneFormState,
} from './setupWizardTypes'
import type { SetupWizardDataApiClient, SetupWizardDataLoaderActions } from './setupWizardDataLoaders'
import {
  createSetupWizardGreenhouseZoneCommands,
  type SetupWizardGreenhouseZoneCommandActions,
} from './setupWizardGreenhouseZoneCommands'
import {
  createSetupWizardPlantNodeCommands,
  type SetupWizardPlantNodeCommandActions,
} from './setupWizardPlantNodeCommands'

interface SetupWizardEntityCommandsOptions {
  api: SetupWizardDataApiClient
  loading: SetupWizardLoadingState
  canConfigure: ComputedRef<boolean>
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  generatedGreenhouseUid: ComputedRef<string>
  availablePlants: Ref<Plant[]>
  selectedGreenhouseId: Ref<number | null>
  selectedZoneId: Ref<number | null>
  selectedPlantId: Ref<number | null>
  selectedGreenhouse: Ref<Greenhouse | null>
  selectedZone: Ref<Zone | null>
  selectedPlant: Ref<Plant | null>
  selectedNodeIds: Ref<number[]>
  attachedNodesCount: Ref<number>
  greenhouseForm: GreenhouseFormState
  zoneForm: ZoneFormState
  plantForm: PlantFormState
  loaders: Pick<
    SetupWizardDataLoaderActions,
    'loadGreenhouses' | 'loadZones' | 'loadPlants' | 'loadAvailableNodes'
  >
}

export type SetupWizardEntityCommandActions = SetupWizardGreenhouseZoneCommandActions & SetupWizardPlantNodeCommandActions

export function createSetupWizardEntityCommands(
  options: SetupWizardEntityCommandsOptions
): SetupWizardEntityCommandActions {
  const greenhouseZoneCommands = createSetupWizardGreenhouseZoneCommands({
    api: options.api,
    loading: options.loading,
    canConfigure: options.canConfigure,
    showToast: options.showToast,
    generatedGreenhouseUid: options.generatedGreenhouseUid,
    selectedGreenhouseId: options.selectedGreenhouseId,
    selectedZoneId: options.selectedZoneId,
    selectedGreenhouse: options.selectedGreenhouse,
    selectedZone: options.selectedZone,
    greenhouseForm: options.greenhouseForm,
    zoneForm: options.zoneForm,
    loaders: {
      loadGreenhouses: options.loaders.loadGreenhouses,
      loadZones: options.loaders.loadZones,
    },
  })

  const plantNodeCommands = createSetupWizardPlantNodeCommands({
    api: options.api,
    loading: options.loading,
    canConfigure: options.canConfigure,
    showToast: options.showToast,
    availablePlants: options.availablePlants,
    selectedPlantId: options.selectedPlantId,
    selectedZone: options.selectedZone,
    selectedPlant: options.selectedPlant,
    selectedNodeIds: options.selectedNodeIds,
    attachedNodesCount: options.attachedNodesCount,
    plantForm: options.plantForm,
    loaders: {
      loadPlants: options.loaders.loadPlants,
      loadAvailableNodes: options.loaders.loadAvailableNodes,
    },
  })

  return {
    ...greenhouseZoneCommands,
    ...plantNodeCommands,
  }
}
