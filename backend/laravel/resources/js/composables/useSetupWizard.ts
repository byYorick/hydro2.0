import { computed, onMounted, reactive, ref, watch } from 'vue'
import { router, usePage } from '@inertiajs/vue3'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { generateUid } from '@/utils/transliterate'
import { createSetupWizardDataFlows } from './setupWizardDataFlows'
import { createSetupWizardRecipeAutomationFlows } from './setupWizardRecipeAutomationFlows'
import { extractZoneActiveCycleStatus, isZoneCycleBlocking, zoneCycleStatusLabel } from './setupWizardZoneCycleGuard'
import type {
  AutomationFormState,
  Greenhouse,
  GreenhouseFormState,
  GreenhouseType,
  Mode,
  Node,
  Plant,
  PlantFormState,
  Recipe,
  RecipeFormState,
  SetupWizardLoadingState,
  SystemType,
  Zone,
  ZoneFormState,
} from './setupWizardTypes'

export type { Mode, SystemType, Greenhouse, GreenhouseType, Zone, Plant, Recipe, Node, RecipePhaseForm } from './setupWizardTypes'

export function useSetupWizard() {
  const page = usePage<{ auth?: { user?: { role?: string } } }>()
  const role = computed(() => page.props.auth?.user?.role ?? 'viewer')
  const canConfigure = computed(() => role.value === 'agronomist' || role.value === 'admin')

  const { showToast } = useToast()
  const { api } = useApi(showToast)

  const loading = reactive<SetupWizardLoadingState>({
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
  })

  const greenhouseMode = ref<Mode>('select')
  const zoneMode = ref<Mode>('select')
  const plantMode = ref<Mode>('select')
  const recipeMode = ref<Mode>('select')

  const availableGreenhouses = ref<Greenhouse[]>([])
  const availableGreenhouseTypes = ref<GreenhouseType[]>([])
  const availableZones = ref<Zone[]>([])
  const availablePlants = ref<Plant[]>([])
  const availableRecipes = ref<Recipe[]>([])
  const availableNodes = ref<Node[]>([])

  const selectedGreenhouseId = ref<number | null>(null)
  const selectedZoneId = ref<number | null>(null)
  const selectedPlantId = ref<number | null>(null)
  const selectedRecipeId = ref<number | null>(null)

  const selectedGreenhouse = ref<Greenhouse | null>(null)
  const selectedZone = ref<Zone | null>(null)
  const selectedPlant = ref<Plant | null>(null)
  const selectedRecipe = ref<Recipe | null>(null)

  const selectedNodeIds = ref<number[]>([])
  const attachedNodesCount = ref<number>(0)

  const greenhouseForm = reactive<GreenhouseFormState>({
    name: '',
    timezone: 'Europe/Moscow',
    greenhouse_type_id: null,
    description: '',
  })

  const zoneForm = reactive<ZoneFormState>({
    name: 'Зона A',
    description: 'Основная зона выращивания',
  })

  const plantForm = reactive<PlantFormState>({
    name: '',
    species: '',
    variety: '',
  })

  const recipeForm = reactive<RecipeFormState>({
    name: 'Базовый рецепт',
    description: 'Рецепт для автоматического полива',
    phases: [
      {
        phase_index: 0,
        name: 'Фаза 1',
        duration_hours: 168,
        targets: {
          ph: 5.8,
          ec: 1.4,
          temp_air: 23,
          humidity_air: 62,
          light_hours: 16,
          irrigation_interval_sec: 900,
          irrigation_duration_sec: 15,
        },
      },
    ],
  })

  const automationForm = reactive<AutomationFormState>({
    systemType: 'drip' as SystemType,
    manageClimate: true,
    manageLighting: true,
    targetPh: 5.8,
    targetEc: 1.6,
    dayTemp: 23,
    dayHumidity: 62,
    ventMinPercent: 15,
    ventMaxPercent: 85,
    luxDay: 18000,
    intervalMinutes: 30,
    durationSeconds: 120,
    cleanTankFillL: 300,
    nutrientTankFillL: 280,
    drainTargetPercent: 20,
  })

  const automationAppliedAt = ref<string | null>(null)

  const stepGreenhouseDone = computed(() => selectedGreenhouse.value !== null)
  const stepZoneDone = computed(() => selectedZone.value !== null)
  const stepPlantDone = computed(() => selectedPlant.value !== null)
  const stepRecipeDone = computed(() => selectedRecipe.value !== null)
  const stepDevicesDone = computed(() => attachedNodesCount.value >= 4)
  const stepAutomationDone = computed(() => automationAppliedAt.value !== null)
  const selectedZoneActiveCycleStatus = computed(() => extractZoneActiveCycleStatus(selectedZone.value))
  const selectedZoneHasActiveCycle = computed(() => isZoneCycleBlocking(selectedZoneActiveCycleStatus.value))
  const launchBlockedReason = computed(() => {
    if (!selectedZoneHasActiveCycle.value) {
      return null
    }

    return `В зоне уже есть активный цикл (${zoneCycleStatusLabel(selectedZoneActiveCycleStatus.value)}). Завершите, поставьте на паузу или прервите цикл перед новым запуском.`
  })

  const canLaunch = computed(() => {
    return stepGreenhouseDone.value
      && stepZoneDone.value
      && stepPlantDone.value
      && stepRecipeDone.value
      && stepDevicesDone.value
      && stepAutomationDone.value
      && !selectedZoneHasActiveCycle.value
  })

  const completedSteps = computed(() => {
    return [
      stepGreenhouseDone.value,
      stepZoneDone.value,
      stepPlantDone.value,
      stepRecipeDone.value,
      stepDevicesDone.value,
      stepAutomationDone.value,
      canLaunch.value,
    ].filter(Boolean).length
  })

  const progressPercent = computed(() => Math.round((completedSteps.value / 6) * 100))

  const launchChecklist = computed(() => [
    { id: 'greenhouse', label: 'Теплица', done: stepGreenhouseDone.value },
    { id: 'zone', label: 'Зона', done: stepZoneDone.value },
    { id: 'plant', label: 'Растение + рецепт', done: stepPlantDone.value && stepRecipeDone.value },
    { id: 'automation', label: 'Логика автоматики', done: stepAutomationDone.value },
    { id: 'devices', label: 'Устройства', done: stepDevicesDone.value },
  ])

  const stepItems = computed(() => [
    { id: 'greenhouse', title: '1. Теплица', hint: 'Контур запуска и структура', done: stepGreenhouseDone.value },
    { id: 'zone', title: '2. Зона', hint: 'Рабочая зона выращивания', done: stepZoneDone.value },
    { id: 'plant', title: '3. Культура и рецепт', hint: 'Рецепт подтягивается по выбранной культуре', done: stepPlantDone.value && stepRecipeDone.value },
    { id: 'devices', title: '4. Устройства', hint: 'Привязка оборудования', done: stepDevicesDone.value },
    { id: 'automation', title: '5. Автоматизация', hint: 'Климат, вода, свет', done: stepAutomationDone.value },
    { id: 'launch', title: '6. Запуск', hint: 'Открыть мастер цикла', done: canLaunch.value },
  ])

  const waterTopologyLabel = computed(() => {
    if (automationForm.systemType === 'drip') {
      return '2 бака: чистая вода + готовый раствор'
    }

    return '3 бака: чистая вода + раствор + дренаж'
  })

  const generatedGreenhouseUid = computed(() => {
    return greenhouseForm.name.trim() ? generateUid(greenhouseForm.name, 'gh-') : 'gh-...'
  })

  const generatedZoneUid = computed(() => {
    return zoneForm.name.trim() ? generateUid(zoneForm.name, 'zn-') : 'zn-...'
  })

  const dataFlows = createSetupWizardDataFlows({
    api,
    loading,
    canConfigure,
    showToast,
    generatedGreenhouseUid,
    availableGreenhouses,
    availableGreenhouseTypes,
    availableZones,
    availablePlants,
    availableRecipes,
    availableNodes,
    selectedGreenhouseId,
    selectedZoneId,
    selectedPlantId,
    selectedGreenhouse,
    selectedZone,
    selectedPlant,
    selectedNodeIds,
    attachedNodesCount,
    greenhouseForm,
    zoneForm,
    plantForm,
  })

  const recipeAutomationFlows = createSetupWizardRecipeAutomationFlows({
    api,
    loading,
    canConfigure,
    showToast,
    recipeForm,
    availableRecipes,
    selectedPlant,
    selectedPlantId,
    selectedRecipeId,
    selectedRecipe,
    automationForm,
    selectedZone,
    selectedZoneActiveCycleStatus,
    selectedZoneHasActiveCycle,
    automationAppliedAt,
    loadRecipes: dataFlows.loadRecipes,
    visit: (url) => router.visit(url),
  })

  watch(
    () => selectedPlant.value?.id,
    async (plantId) => {
      if (!plantId) {
        selectedRecipe.value = null
        selectedRecipeId.value = null
        return
      }

      await recipeAutomationFlows.ensureRecipeForPlant(true)
    }
  )

  watch(
    () => selectedRecipeId.value,
    async (recipeId) => {
      if (!recipeId) {
        return
      }

      let recipe = availableRecipes.value.find((item) => item.id === recipeId) ?? null
      const hasPhases = Array.isArray(recipe?.phases) && recipe.phases.length > 0

      if (!hasPhases) {
        const detailedRecipe = await recipeAutomationFlows.loadRecipeDetails(recipeId)
        if (detailedRecipe) {
          recipe = detailedRecipe
        }
      }

      if (recipe) {
        selectedRecipe.value = recipe
        recipeAutomationFlows.syncAutomationFromRecipe(recipe)
      }
    }
  )

  watch(selectedGreenhouseId, async (greenhouseId) => {
    selectedZoneId.value = null
    selectedZone.value = null
    selectedNodeIds.value = []
    attachedNodesCount.value = 0
    automationAppliedAt.value = null

    if (!greenhouseId || greenhouseMode.value !== 'select') {
      availableZones.value = []
      return
    }

    zoneMode.value = 'select'
    await dataFlows.loadZones(greenhouseId)
  })

  watch(selectedZoneId, (zoneId, previousZoneId) => {
    if (zoneId === previousZoneId) {
      return
    }

    if (selectedZone.value?.id && selectedZone.value.id !== zoneId) {
      selectedZone.value = null
    }

    selectedNodeIds.value = []
    attachedNodesCount.value = 0
    automationAppliedAt.value = null
  })

  watch(
    () => automationForm.systemType,
    (type) => {
      if (type === 'drip') {
        automationForm.drainTargetPercent = 0
      } else if (automationForm.drainTargetPercent <= 0) {
        automationForm.drainTargetPercent = 20
      }
    }
  )

  onMounted(async () => {
    await Promise.all([
      dataFlows.loadGreenhouseTypes(),
      dataFlows.loadGreenhouses(),
      dataFlows.loadPlants(),
      dataFlows.loadRecipes(),
      dataFlows.loadAvailableNodes(),
    ])

    if (!greenhouseForm.greenhouse_type_id && availableGreenhouseTypes.value.length > 0) {
      greenhouseForm.greenhouse_type_id = availableGreenhouseTypes.value[0].id
    }
  })

  function formatDateTime(value: string | null): string {
    if (!value) {
      return '-'
    }

    return new Date(value).toLocaleString('ru-RU')
  }

  return {
    role,
    canConfigure,
    loading,
    greenhouseMode,
    zoneMode,
    plantMode,
    recipeMode,
    availableGreenhouses,
    availableGreenhouseTypes,
    availableZones,
    availablePlants,
    availableRecipes,
    availableNodes,
    selectedGreenhouseId,
    selectedZoneId,
    selectedPlantId,
    selectedRecipeId,
    selectedGreenhouse,
    selectedZone,
    selectedPlant,
    selectedRecipe,
    selectedNodeIds,
    attachedNodesCount,
    greenhouseForm,
    zoneForm,
    plantForm,
    recipeForm,
    automationForm,
    automationAppliedAt,
    stepGreenhouseDone,
    stepZoneDone,
    stepPlantDone,
    stepRecipeDone,
    stepDevicesDone,
    stepAutomationDone,
    selectedZoneActiveCycleStatus,
    selectedZoneHasActiveCycle,
    launchBlockedReason,
    completedSteps,
    progressPercent,
    canLaunch,
    launchChecklist,
    stepItems,
    waterTopologyLabel,
    generatedGreenhouseUid,
    generatedZoneUid,
    addRecipePhase: recipeAutomationFlows.addRecipePhase,
    createGreenhouse: dataFlows.createGreenhouse,
    selectGreenhouse: dataFlows.selectGreenhouse,
    createZone: dataFlows.createZone,
    selectZone: dataFlows.selectZone,
    createPlant: dataFlows.createPlant,
    selectPlant: dataFlows.selectPlant,
    createRecipe: recipeAutomationFlows.createRecipe,
    selectRecipe: recipeAutomationFlows.selectRecipe,
    attachNodesToZone: dataFlows.attachNodesToZone,
    refreshAvailableNodes: dataFlows.loadAvailableNodes,
    applyAutomation: recipeAutomationFlows.applyAutomation,
    openCycleWizard: recipeAutomationFlows.openCycleWizard,
    formatDateTime,
  }
}
