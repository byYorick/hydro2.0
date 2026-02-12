import type { ComputedRef, Ref } from 'vue'
import type { ToastVariant } from '@/composables/useToast'
import type {
  Greenhouse,
  GreenhouseType,
  GreenhouseFormState,
  Node,
  Plant,
  PlantFormState,
  Recipe,
  SetupWizardDeviceAssignments,
  SetupWizardLoadingState,
  Zone,
  ZoneFormState,
} from './setupWizardTypes'
import {
  createSetupWizardDataLoaders,
  type SetupWizardDataApiClient,
  type SetupWizardDataLoaderActions,
} from './setupWizardDataLoaders'
import { createSetupWizardEntityCommands } from './setupWizardEntityCommands'

interface SetupWizardDataFlowsOptions {
  api: SetupWizardDataApiClient
  loading: SetupWizardLoadingState
  canConfigure: ComputedRef<boolean>
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  generatedGreenhouseUid: ComputedRef<string>
  availableGreenhouses: Ref<Greenhouse[]>
  availableGreenhouseTypes: Ref<GreenhouseType[]>
  availableZones: Ref<Zone[]>
  availablePlants: Ref<Plant[]>
  availableRecipes: Ref<Recipe[]>
  availableNodes: Ref<Node[]>
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
}

export type SetupWizardDataFlowActions = SetupWizardDataLoaderActions & {
  createGreenhouse: () => Promise<void>
  selectGreenhouse: () => Promise<void>
  createZone: () => Promise<void>
  selectZone: () => Promise<void>
  createPlant: () => Promise<void>
  selectPlant: () => void
  attachNodesToZone: (assignments?: SetupWizardDeviceAssignments | null) => Promise<void>
}

export function createSetupWizardDataFlows(options: SetupWizardDataFlowsOptions): SetupWizardDataFlowActions {
  const loaders = createSetupWizardDataLoaders({
    api: options.api,
    loading: options.loading,
    showToast: options.showToast,
    availableGreenhouses: options.availableGreenhouses,
    availableGreenhouseTypes: options.availableGreenhouseTypes,
    availableZones: options.availableZones,
    availablePlants: options.availablePlants,
    availableRecipes: options.availableRecipes,
    availableNodes: options.availableNodes,
    selectedGreenhouse: options.selectedGreenhouse,
  })

  const commands = createSetupWizardEntityCommands({
    api: options.api,
    loading: options.loading,
    canConfigure: options.canConfigure,
    showToast: options.showToast,
    generatedGreenhouseUid: options.generatedGreenhouseUid,
    availableNodes: options.availableNodes,
    availablePlants: options.availablePlants,
    selectedGreenhouseId: options.selectedGreenhouseId,
    selectedZoneId: options.selectedZoneId,
    selectedPlantId: options.selectedPlantId,
    selectedGreenhouse: options.selectedGreenhouse,
    selectedZone: options.selectedZone,
    selectedPlant: options.selectedPlant,
    selectedNodeIds: options.selectedNodeIds,
    attachedNodesCount: options.attachedNodesCount,
    greenhouseForm: options.greenhouseForm,
    zoneForm: options.zoneForm,
    plantForm: options.plantForm,
    loaders,
  })

  return {
    ...loaders,
    ...commands,
  }
}
