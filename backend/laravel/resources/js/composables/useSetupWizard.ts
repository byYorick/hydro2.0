import { computed, onMounted, reactive, ref, watch } from 'vue'
import { router, usePage } from '@inertiajs/vue3'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { extractData } from '@/utils/apiHelpers'
import { generateUid } from '@/utils/transliterate'
import { logger } from '@/utils/logger'

export type Mode = 'select' | 'create'
export type SystemType = 'drip' | 'substrate_trays' | 'nft'

export interface Greenhouse {
  id: number
  uid: string
  name: string
  type?: string
  description?: string
}

export interface Zone {
  id: number
  name: string
  greenhouse_id: number
}

export interface Plant {
  id: number
  name: string
}

export interface Recipe {
  id: number
  name: string
  phases_count?: number
}

export interface Node {
  id: number
  uid?: string
  name?: string
  type?: string
}

export interface RecipePhaseForm {
  phase_index: number
  name: string
  duration_hours: number
  targets: {
    ph: number
    ec: number
    temp_air: number
    humidity_air: number
    light_hours: number
    irrigation_interval_sec: number
    irrigation_duration_sec: number
  }
}

export function useSetupWizard() {
const page = usePage<{ auth?: { user?: { role?: string } } }>()
const role = computed(() => page.props.auth?.user?.role ?? 'viewer')
const canConfigure = computed(() => role.value === 'agronomist' || role.value === 'admin')

const { showToast } = useToast()
const { api } = useApi(showToast)

const loading = reactive({
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
const zoneMode = ref<Mode>('create')
const plantMode = ref<Mode>('select')
const recipeMode = ref<Mode>('select')

const availableGreenhouses = ref<Greenhouse[]>([])
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

const greenhouseForm = reactive({
  name: '',
  timezone: 'Europe/Moscow',
  type: 'indoor',
  description: '',
})

const zoneForm = reactive({
  name: 'Зона A',
  description: 'Основная зона выращивания',
})

const plantForm = reactive({
  name: '',
  species: '',
  variety: '',
})

const recipeForm = reactive({
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
  ] as RecipePhaseForm[],
})

const automationForm = reactive({
  systemType: 'drip' as SystemType,
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
const stepDevicesDone = computed(() => attachedNodesCount.value > 0 || availableNodes.value.length === 0)
const stepAutomationDone = computed(() => automationAppliedAt.value !== null)

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

const progressPercent = computed(() => Math.round((completedSteps.value / 7) * 100))

const canLaunch = computed(() => {
  return stepGreenhouseDone.value
    && stepZoneDone.value
    && stepPlantDone.value
    && stepRecipeDone.value
    && stepAutomationDone.value
})

const launchChecklist = computed(() => [
  { id: 'greenhouse', label: 'Теплица', done: stepGreenhouseDone.value },
  { id: 'zone', label: 'Зона', done: stepZoneDone.value },
  { id: 'plant', label: 'Растение', done: stepPlantDone.value },
  { id: 'recipe', label: 'Рецепт', done: stepRecipeDone.value },
  { id: 'automation', label: 'Логика автоматики', done: stepAutomationDone.value },
  { id: 'devices', label: 'Устройства', done: stepDevicesDone.value },
])

const stepItems = computed(() => [
  { id: 'greenhouse', title: '1. Теплица', hint: 'Контур запуска и структура', done: stepGreenhouseDone.value },
  { id: 'zone', title: '2. Зона', hint: 'Рабочая зона выращивания', done: stepZoneDone.value },
  { id: 'plant', title: '3. Растение', hint: 'Культура и профиль', done: stepPlantDone.value },
  { id: 'recipe', title: '4. Рецепт', hint: 'Фазы и целевые параметры', done: stepRecipeDone.value },
  { id: 'devices', title: '5. Устройства', hint: 'Привязка оборудования', done: stepDevicesDone.value },
  { id: 'automation', title: '6. Автоматизация', hint: 'Климат, вода, свет', done: stepAutomationDone.value },
  { id: 'launch', title: '7. Запуск', hint: 'Открыть мастер цикла', done: canLaunch.value },
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

watch(selectedGreenhouseId, async (greenhouseId) => {
  if (!greenhouseId || greenhouseMode.value !== 'select') return
  await loadZones(greenhouseId)
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
    loadGreenhouses(),
    loadPlants(),
    loadRecipes(),
    loadAvailableNodes(),
  ])
})

function addRecipePhase(): void {
  const maxIndex = recipeForm.phases.length > 0
    ? Math.max(...recipeForm.phases.map((phase) => phase.phase_index))
    : -1

  recipeForm.phases.push({
    phase_index: maxIndex + 1,
    name: `Фаза ${maxIndex + 2}`,
    duration_hours: 72,
    targets: {
      ph: 5.8,
      ec: 1.6,
      temp_air: 23,
      humidity_air: 62,
      light_hours: 16,
      irrigation_interval_sec: 900,
      irrigation_duration_sec: 15,
    },
  })
}

async function loadGreenhouses(): Promise<void> {
  loading.greenhouses = true
  try {
    const response = await api.get('/greenhouses')
    const data = extractData<Greenhouse[]>(response.data) || []
    availableGreenhouses.value = Array.isArray(data) ? data : []
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to load greenhouses', { error })
    availableGreenhouses.value = []
  } finally {
    loading.greenhouses = false
  }
}

async function loadZones(greenhouseId?: number): Promise<void> {
  const targetGreenhouseId = greenhouseId ?? selectedGreenhouse.value?.id
  if (!targetGreenhouseId) return

  loading.zones = true
  try {
    const response = await api.get('/zones', {
      params: { greenhouse_id: targetGreenhouseId },
    })

    const payload = extractData<any>(response.data)
    if (Array.isArray(payload)) {
      availableZones.value = payload as Zone[]
    } else if (payload && Array.isArray(payload.data)) {
      availableZones.value = payload.data as Zone[]
    } else {
      availableZones.value = []
    }
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
    const payload = extractData<any>(response.data)
    if (Array.isArray(payload)) {
      availablePlants.value = payload as Plant[]
    } else if (payload && Array.isArray(payload.data)) {
      availablePlants.value = payload.data as Plant[]
    } else {
      availablePlants.value = []
    }
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
    const payload = extractData<any>(response.data)
    if (Array.isArray(payload)) {
      availableRecipes.value = payload as Recipe[]
    } else if (payload && Array.isArray(payload.data)) {
      availableRecipes.value = payload.data as Recipe[]
    } else {
      availableRecipes.value = []
    }
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

    const payload = extractData<any>(response.data)
    if (Array.isArray(payload)) {
      availableNodes.value = payload as Node[]
    } else if (payload && Array.isArray(payload.data)) {
      availableNodes.value = payload.data as Node[]
    } else {
      availableNodes.value = []
    }
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to load nodes', { error })
    availableNodes.value = []
  } finally {
    loading.nodes = false
  }
}

async function createGreenhouse(): Promise<void> {
  if (!canConfigure.value || !greenhouseForm.name.trim()) return

  loading.stepGreenhouse = true
  try {
    const response = await api.post('/greenhouses', {
      ...greenhouseForm,
      uid: generatedGreenhouseUid.value,
    })

    const greenhouse = extractData<Greenhouse>(response.data)
    if (!greenhouse?.id) {
      throw new Error('Greenhouse not returned from API')
    }

    selectedGreenhouse.value = greenhouse
    selectedGreenhouseId.value = greenhouse.id
    showToast('Теплица создана', 'success', TOAST_TIMEOUT.NORMAL)

    await loadGreenhouses()
    await loadZones(greenhouse.id)
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to create greenhouse', { error })
  } finally {
    loading.stepGreenhouse = false
  }
}

async function selectGreenhouse(): Promise<void> {
  if (!canConfigure.value || !selectedGreenhouseId.value) return

  loading.stepGreenhouse = true
  try {
    const response = await api.get(`/greenhouses/${selectedGreenhouseId.value}`)
    const greenhouse = extractData<Greenhouse>(response.data)
    if (!greenhouse?.id) {
      throw new Error('Greenhouse not found')
    }

    selectedGreenhouse.value = greenhouse
    showToast('Теплица выбрана', 'success', TOAST_TIMEOUT.NORMAL)
    await loadZones(greenhouse.id)
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to select greenhouse', { error })
  } finally {
    loading.stepGreenhouse = false
  }
}

async function createZone(): Promise<void> {
  if (!canConfigure.value || !selectedGreenhouse.value?.id || !zoneForm.name.trim()) return

  loading.stepZone = true
  try {
    const response = await api.post('/zones', {
      name: zoneForm.name,
      description: zoneForm.description,
      greenhouse_id: selectedGreenhouse.value.id,
    })

    const zone = extractData<Zone>(response.data)
    if (!zone?.id) {
      throw new Error('Zone not returned from API')
    }

    selectedZone.value = zone
    selectedZoneId.value = zone.id
    showToast('Зона создана', 'success', TOAST_TIMEOUT.NORMAL)

    await loadZones(selectedGreenhouse.value.id)
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to create zone', { error })
  } finally {
    loading.stepZone = false
  }
}

async function selectZone(): Promise<void> {
  if (!canConfigure.value || !selectedZoneId.value) return

  loading.stepZone = true
  try {
    const response = await api.get(`/zones/${selectedZoneId.value}`)
    const zone = extractData<Zone>(response.data)
    if (!zone?.id) {
      throw new Error('Zone not found')
    }

    selectedZone.value = zone
    showToast('Зона выбрана', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to select zone', { error })
  } finally {
    loading.stepZone = false
  }
}

async function createPlant(): Promise<void> {
  if (!canConfigure.value || !plantForm.name.trim()) return

  loading.stepPlant = true
  try {
    const response = await api.post('/plants', {
      name: plantForm.name,
      species: plantForm.species || null,
      variety: plantForm.variety || null,
    })

    const payload = extractData<any>(response.data)
    const plantId = payload?.id

    if (!plantId) {
      throw new Error('Plant id missing in response')
    }

    selectedPlant.value = {
      id: plantId,
      name: plantForm.name,
    }
    selectedPlantId.value = plantId

    showToast('Растение создано', 'success', TOAST_TIMEOUT.NORMAL)
    await loadPlants()
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to create plant', { error })
  } finally {
    loading.stepPlant = false
  }
}

function selectPlant(): void {
  if (!canConfigure.value || !selectedPlantId.value) return

  const plant = availablePlants.value.find((item) => item.id === selectedPlantId.value)
  if (!plant) return

  selectedPlant.value = plant
  showToast('Растение выбрано', 'success', TOAST_TIMEOUT.NORMAL)
}

async function createRecipe(): Promise<void> {
  if (!canConfigure.value || !recipeForm.name.trim()) return

  loading.stepRecipe = true
  try {
    const recipeResponse = await api.post('/recipes', {
      name: recipeForm.name,
      description: recipeForm.description,
    })

    const recipePayload = extractData<any>(recipeResponse.data)
    const recipeId = recipePayload?.id
    if (!recipeId) {
      throw new Error('Recipe ID missing')
    }

    const revisionResponse = await api.post(`/recipes/${recipeId}/revisions`, {
      description: 'Initial revision from setup wizard',
    })

    const revisionPayload = extractData<any>(revisionResponse.data)
    const revisionId = revisionPayload?.id
    if (!revisionId) {
      throw new Error('Recipe revision ID missing')
    }

    for (const phase of recipeForm.phases) {
      await api.post(`/recipe-revisions/${revisionId}/phases`, {
        phase_index: phase.phase_index,
        name: phase.name || `Фаза ${phase.phase_index + 1}`,
        duration_hours: phase.duration_hours,
        ph_target: phase.targets.ph,
        ph_min: phase.targets.ph,
        ph_max: phase.targets.ph,
        ec_target: phase.targets.ec,
        ec_min: phase.targets.ec,
        ec_max: phase.targets.ec,
        temp_air_target: phase.targets.temp_air,
        humidity_target: phase.targets.humidity_air,
        lighting_photoperiod_hours: phase.targets.light_hours,
        irrigation_interval_sec: phase.targets.irrigation_interval_sec,
        irrigation_duration_sec: phase.targets.irrigation_duration_sec,
      })
    }

    await api.post(`/recipe-revisions/${revisionId}/publish`)

    const recipeDetailsResponse = await api.get(`/recipes/${recipeId}`)
    const recipe = extractData<Recipe>(recipeDetailsResponse.data)
    if (!recipe?.id) {
      throw new Error('Recipe details not returned')
    }

    selectedRecipe.value = recipe
    selectedRecipeId.value = recipe.id
    showToast('Рецепт создан', 'success', TOAST_TIMEOUT.NORMAL)
    await loadRecipes()
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to create recipe', { error })
  } finally {
    loading.stepRecipe = false
  }
}

function selectRecipe(): void {
  if (!canConfigure.value || !selectedRecipeId.value) return

  const recipe = availableRecipes.value.find((item) => item.id === selectedRecipeId.value)
  if (!recipe) return

  selectedRecipe.value = recipe
  showToast('Рецепт выбран', 'success', TOAST_TIMEOUT.NORMAL)
}

async function attachNodesToZone(): Promise<void> {
  if (!canConfigure.value || !selectedZone.value?.id || selectedNodeIds.value.length === 0) return

  loading.stepDevices = true
  try {
    await Promise.all(
      selectedNodeIds.value.map((nodeId) => api.patch(`/nodes/${nodeId}`, { zone_id: selectedZone.value?.id }))
    )

    attachedNodesCount.value = selectedNodeIds.value.length
    showToast(`Привязано узлов: ${attachedNodesCount.value}`, 'success', TOAST_TIMEOUT.NORMAL)

    selectedNodeIds.value = []
    await loadAvailableNodes()
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to attach nodes', { error })
  } finally {
    loading.stepDevices = false
  }
}

async function applyAutomation(): Promise<void> {
  if (!canConfigure.value || !selectedZone.value?.id) return

  if (automationForm.ventMinPercent > automationForm.ventMaxPercent) {
    showToast('Минимальное открытие форточки не может быть больше максимального', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  loading.stepAutomation = true
  try {
    const tanksCount = automationForm.systemType === 'drip' ? 2 : 3

    await api.post(`/zones/${selectedZone.value.id}/commands`, {
      type: 'GROWTH_CYCLE_CONFIG',
      params: {
        mode: 'adjust',
        subsystems: {
          ph: {
            enabled: true,
            targets: {
              min: Number((automationForm.targetPh - 0.2).toFixed(2)),
              max: Number((automationForm.targetPh + 0.2).toFixed(2)),
              target: Number(automationForm.targetPh.toFixed(2)),
            },
          },
          ec: {
            enabled: true,
            targets: {
              min: Number((automationForm.targetEc - 0.2).toFixed(2)),
              max: Number((automationForm.targetEc + 0.2).toFixed(2)),
              target: Number(automationForm.targetEc.toFixed(2)),
            },
          },
          irrigation: {
            enabled: true,
            targets: {
              interval_minutes: automationForm.intervalMinutes,
              duration_seconds: automationForm.durationSeconds,
              system_type: automationForm.systemType,
              tanks_count: tanksCount,
              clean_tank_fill_l: automationForm.cleanTankFillL,
              nutrient_tank_target_l: automationForm.nutrientTankFillL,
              fill_strategy: 'volume',
              correction_strategy: 'feedback_target',
              drain_control: {
                enabled: tanksCount === 3,
                target_percent: tanksCount === 3 ? automationForm.drainTargetPercent : 0,
              },
              correction_node: {
                target_ph: Number(automationForm.targetPh.toFixed(2)),
                target_ec: Number(automationForm.targetEc.toFixed(2)),
                sensors_location: 'correction_node',
              },
            },
          },
          climate: {
            enabled: true,
            targets: {
              temperature: automationForm.dayTemp,
              humidity: automationForm.dayHumidity,
              vent_control: {
                min_open_percent: automationForm.ventMinPercent,
                max_open_percent: automationForm.ventMaxPercent,
              },
              external_guard: {
                enabled: true,
              },
            },
          },
          lighting: {
            enabled: true,
            targets: {
              lux_target_day: automationForm.luxDay,
              future_metrics: {
                ppfd: null,
                dli: null,
              },
            },
          },
        },
      },
    })

    automationAppliedAt.value = new Date().toISOString()
    showToast('Логика автоматики применена', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (error) {
    logger.error('[Setup/Wizard] Failed to apply automation profile', { error })
  } finally {
    loading.stepAutomation = false
  }
}

async function openCycleWizard(): Promise<void> {
  if (!selectedZone.value?.id || !selectedRecipe.value?.id) {
    showToast('Сначала выберите зону и рецепт', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  loading.stepLaunch = true
  try {
    const url = `/zones/${selectedZone.value.id}?start_cycle=1&recipe_id=${selectedRecipe.value.id}`
    showToast('Открываю мастер запуска цикла', 'info', TOAST_TIMEOUT.NORMAL)
    router.visit(url)
  } finally {
    loading.stepLaunch = false
  }
}

function formatDateTime(value: string | null): string {
  if (!value) return '-'
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
    completedSteps,
    progressPercent,
    canLaunch,
    launchChecklist,
    stepItems,
    waterTopologyLabel,
    generatedGreenhouseUid,
    addRecipePhase,
    createGreenhouse,
    selectGreenhouse,
    createZone,
    selectZone,
    createPlant,
    selectPlant,
    createRecipe,
    selectRecipe,
    attachNodesToZone,
    applyAutomation,
    openCycleWizard,
    formatDateTime,
  }
}
