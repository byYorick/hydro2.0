import { computed, onMounted, reactive, ref, watch } from 'vue'
import { router, usePage } from '@inertiajs/vue3'
import { useApi } from '@/composables/useApi'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import { useToast } from '@/composables/useToast'
import { extractData } from '@/utils/apiHelpers'
import { generateUid } from '@/utils/transliterate'
import { createSetupWizardDataFlows } from './setupWizardDataFlows'
import { createSetupWizardRecipeAutomationFlows } from './setupWizardRecipeAutomationFlows'
import { extractZoneActiveCycleStatus, isZoneCycleBlocking, zoneCycleStatusLabel } from './setupWizardZoneCycleGuard'
import {
  asRecord,
  GREENHOUSE_LOGIC_PROFILE_NAMESPACE,
  payloadFromGreenhouseLogicDocument,
  resolveGreenhouseProfileEntry,
  toNodeIdArray,
  type GreenhouseClimateBindingsState,
} from './greenhouseLogicProfileAuthority'
import { applyAutomationFromRecipe, buildGrowthCycleConfigPayload, syncSystemToTankLayout } from './zoneAutomationFormLogic'
import type {
  Greenhouse,
  GreenhouseFormState,
  GreenhouseType,
  Mode,
  Node,
  Plant,
  PlantFormState,
  Recipe,
  RecipeFormState,
  SetupWizardDeviceAssignments,
  SetupWizardLoadingState,
  SystemType,
  Zone,
  ZoneFormState,
} from './setupWizardTypes'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
  ZoneClimateFormState,
} from './zoneAutomationTypes'

export type { Mode, SystemType, Greenhouse, GreenhouseType, Zone, Plant, Recipe, Node, RecipePhaseForm } from './setupWizardTypes'

interface ZoneLaunchReadiness {
  ready: boolean
  checks?: Record<string, boolean>
  errors?: string[]
  warnings?: string[]
  error_details?: Array<Record<string, unknown>>
  blocking_alerts?: Array<Record<string, unknown>>
  dispatch_enabled?: boolean
}

interface ZoneHealthResponse {
  readiness?: ZoneLaunchReadiness | null
}

type ZoneAssignmentRole =
  | 'irrigation'
  | 'ph_correction'
  | 'ec_correction'
  | 'light'
  | 'co2_sensor'
  | 'co2_actuator'
  | 'root_vent_actuator'

const ZONE_ASSIGNMENT_ROLES: ZoneAssignmentRole[] = [
  'irrigation',
  'ph_correction',
  'ec_correction',
  'light',
  'co2_sensor',
  'co2_actuator',
  'root_vent_actuator',
]

const ZONE_ASSIGNMENT_BINDING_ROLES: Record<ZoneAssignmentRole, string[]> = {
  irrigation: ['main_pump', 'drain'],
  ph_correction: ['ph_acid_pump', 'ph_base_pump'],
  ec_correction: ['ec_npk_pump', 'ec_calcium_pump', 'ec_magnesium_pump', 'ec_micro_pump'],
  light: ['light'],
  co2_sensor: ['co2_sensor'],
  co2_actuator: ['co2_actuator'],
  root_vent_actuator: ['root_vent_actuator'],
}


function nodeChannels(node: Node): string[] {
  return Array.isArray(node.channels)
    ? node.channels
      .map((channel) => String(channel.channel ?? '').toLowerCase())
      .filter((channel) => channel.length > 0)
    : []
}

function normalizePositiveInt(value: unknown): number | null {
  const normalized = Number(value)
  return Number.isInteger(normalized) && normalized > 0 ? normalized : null
}

function nodeId(node: Node): number | null {
  return normalizePositiveInt(node.id)
}

function nodeZoneId(node: Node): number | null {
  return normalizePositiveInt(node.zone_id)
}

function nodeBindingRoles(node: Node): string[] {
  return Array.isArray(node.channels)
    ? node.channels
      .map((channel) => String(channel.binding_role ?? '').toLowerCase())
      .filter((role) => role.length > 0)
    : []
}

function hasAnyChannel(node: Node, candidates: string[]): boolean {
  const lookup = new Set(nodeChannels(node))
  return candidates.some((candidate) => lookup.has(candidate))
}

function matchesZoneAssignmentRole(node: Node, role: ZoneAssignmentRole): boolean {
  const type = String(node.type ?? '').toLowerCase()

  if (role === 'irrigation') {
    return type === 'irrig' || hasAnyChannel(node, [
      'pump_main',
      'main_pump',
      'pump_irrigation',
      'valve_irrigation',
      'valve_clean_fill',
      'valve_clean_supply',
      'valve_solution_fill',
      'valve_solution_supply',
      'level_clean_min',
      'level_clean_max',
      'level_solution_min',
      'level_solution_max',
      'water_level',
      'pump_in',
      'drain',
      'drain_main',
    ])
  }

  if (role === 'ph_correction') {
    return type === 'ph' || hasAnyChannel(node, ['ph_sensor', 'pump_acid', 'pump_base'])
  }

  if (role === 'ec_correction') {
    return type === 'ec' || hasAnyChannel(node, ['ec_sensor', 'pump_a', 'pump_b', 'pump_c', 'pump_d'])
  }

  if (role === 'light') {
    return type === 'light' || hasAnyChannel(node, ['light', 'light_main', 'white_light', 'uv_light', 'light_level', 'lux_main'])
  }

  if (role === 'co2_sensor') {
    return type === 'climate' || hasAnyChannel(node, ['co2_ppm'])
  }

  if (role === 'co2_actuator') {
    return type === 'climate' || hasAnyChannel(node, ['co2_inject'])
  }

  return type === 'climate' || hasAnyChannel(node, ['root_vent', 'fan_root'])
}

export function useSetupWizard() {
  const page = usePage<{ auth?: { user?: { role?: string } } }>()
  const role = computed(() => page.props.auth?.user?.role ?? 'viewer')
  const canConfigure = computed(() => role.value === 'agronomist' || role.value === 'admin')

  const { showToast } = useToast()
  const { api } = useApi(showToast)
  const automationConfig = useAutomationConfig(showToast)

  const loading = reactive<SetupWizardLoadingState & { stepGreenhouseClimate: boolean }>({
    greenhouses: false,
    zones: false,
    plants: false,
    recipes: false,
    nodes: false,
    stepGreenhouse: false,
    stepGreenhouseClimate: false,
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
  const greenhouseClimateNodes = ref<Node[]>([])
  const zoneLaunchReadiness = ref<ZoneLaunchReadiness | null>(null)
  const zoneLaunchReadinessLoading = ref(false)

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

  const automationClimateForm = reactive<ClimateFormState>({
    enabled: true,
    dayTemp: 23,
    nightTemp: 20,
    dayHumidity: 62,
    nightHumidity: 70,
    intervalMinutes: 5,
    dayStart: '07:00',
    nightStart: '19:00',
    ventMinPercent: 15,
    ventMaxPercent: 85,
    useExternalTelemetry: true,
    outsideTempMin: 4,
    outsideTempMax: 34,
    outsideHumidityMax: 90,
    manualOverrideEnabled: true,
    overrideMinutes: 30,
  })

  const automationWaterForm = reactive<WaterFormState>({
    systemType: 'drip',
    tanksCount: 2,
    cleanTankFillL: 300,
    nutrientTankTargetL: 280,
    irrigationBatchL: 20,
    intervalMinutes: 30,
    durationSeconds: 120,
    fillTemperatureC: 20,
    fillWindowStart: '05:00',
    fillWindowEnd: '07:00',
    targetPh: 5.8,
    targetEc: 1.6,
    phPct: 5,
    ecPct: 10,
    valveSwitching: true,
    correctionDuringIrrigation: true,
    prepareToleranceEcPct: 10,
    prepareTolerancePhPct: 5,
    correctionMaxEcCorrectionAttempts: 8,
    correctionMaxPhCorrectionAttempts: 8,
    correctionPrepareRecirculationMaxAttempts: 6,
    correctionPrepareRecirculationMaxCorrectionAttempts: 24,
    correctionStabilizationSec: 30,
    enableDrainControl: false,
    drainTargetPercent: 20,
    diagnosticsEnabled: true,
    diagnosticsIntervalMinutes: 15,
    diagnosticsWorkflow: 'startup',
    cleanTankFullThreshold: 0.95,
    refillDurationSeconds: 30,
    refillTimeoutSeconds: 600,
    refillRequiredNodeTypes: 'irrig,climate,light',
    refillPreferredChannel: 'fill_valve',
    startupCleanFillTimeoutSeconds: 1800,
    startupSolutionFillTimeoutSeconds: 1800,
    startupPrepareRecirculationTimeoutSeconds: 900,
    startupCleanFillRetryCycles: 2,
    irrigationRecoveryMaxContinueAttempts: 3,
    irrigationRecoveryTimeoutSeconds: 600,
    solutionChangeEnabled: false,
    solutionChangeIntervalMinutes: 180,
    solutionChangeDurationSeconds: 120,
    manualIrrigationSeconds: 90,
    twoTankCleanFillStartSteps: 1,
    twoTankCleanFillStopSteps: 1,
    twoTankSolutionFillStartSteps: 3,
    twoTankSolutionFillStopSteps: 3,
  })

  const automationLightingForm = reactive<LightingFormState>({
    enabled: false,
    luxDay: 18000,
    luxNight: 0,
    hoursOn: 16,
    intervalMinutes: 30,
    scheduleStart: '06:00',
    scheduleEnd: '22:00',
    manualIntensity: 75,
    manualDurationHours: 4,
  })

  const greenhouseClimateEnabled = ref(false)
  const greenhouseClimateBindings = reactive<GreenhouseClimateBindingsState>({
    climate_sensors: [],
    weather_station_sensors: [],
    vent_actuators: [],
    fan_actuators: [],
  })
  const greenhouseClimateAppliedAt = ref<string | null>(null)

  const zoneClimateForm = reactive<ZoneClimateFormState>({
    enabled: false,
  })

  const deviceAssignments = reactive<SetupWizardDeviceAssignments>({
    irrigation: null,
    ph_correction: null,
    ec_correction: null,
    accumulation: null,
    climate: null,
    light: null,
    co2_sensor: null,
    co2_actuator: null,
    root_vent_actuator: null,
  })

  const automationAppliedAt = ref<string | null>(null)

  const stepGreenhouseDone = computed(() => selectedGreenhouse.value !== null)
  const stepZoneDone = computed(() => selectedZone.value !== null)
  const stepPlantDone = computed(() => selectedPlant.value !== null)
  const stepRecipeDone = computed(() => selectedRecipe.value !== null)

  const greenhouseClimateBindingsReady = computed(() => {
    if (!greenhouseClimateEnabled.value) {
      return true
    }

    return greenhouseClimateBindings.climate_sensors.length > 0
      && (greenhouseClimateBindings.vent_actuators.length > 0 || greenhouseClimateBindings.fan_actuators.length > 0)
  })

  const zoneAutomationExpectedNodeIds = computed(() => {
    const ids = [
      deviceAssignments.irrigation,
      deviceAssignments.ph_correction,
      deviceAssignments.ec_correction,
      automationLightingForm.enabled ? deviceAssignments.light : null,
      zoneClimateForm.enabled ? deviceAssignments.co2_sensor : null,
      zoneClimateForm.enabled ? deviceAssignments.co2_actuator : null,
      zoneClimateForm.enabled ? deviceAssignments.root_vent_actuator : null,
    ].filter((value): value is number => typeof value === 'number')

    return Array.from(new Set(ids))
  })

  const zoneAutomationAssignmentsReady = computed(() => {
    if (
      deviceAssignments.irrigation === null
      || deviceAssignments.ph_correction === null
      || deviceAssignments.ec_correction === null
    ) {
      return false
    }

    if (automationLightingForm.enabled && deviceAssignments.light === null) {
      return false
    }

    if (
      zoneClimateForm.enabled
      && deviceAssignments.co2_sensor === null
      && deviceAssignments.co2_actuator === null
      && deviceAssignments.root_vent_actuator === null
    ) {
      return false
    }

    return true
  })

  const selectedZoneActiveCycleStatus = computed(() => extractZoneActiveCycleStatus(selectedZone.value))
  const selectedZoneHasActiveCycle = computed(() => isZoneCycleBlocking(selectedZoneActiveCycleStatus.value))
  const launchBlockedReason = computed(() => {
    if (!selectedZoneHasActiveCycle.value) {
      return null
    }

    return `В зоне уже есть активный цикл (${zoneCycleStatusLabel(selectedZoneActiveCycleStatus.value)}). Завершите, поставьте на паузу или прервите цикл перед новым запуском.`
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
    greenhouseClimateNodes,
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
    climateForm: automationClimateForm,
    waterForm: automationWaterForm,
    lightingForm: automationLightingForm,
    zoneClimateForm,
    selectedZone,
    selectedZoneActiveCycleStatus,
    selectedZoneHasActiveCycle,
    automationAppliedAt,
    loadRecipes: dataFlows.loadRecipes,
    visit: (url) => router.visit(url),
  })

  const zoneAutomationNodesReady = computed(() => {
    return zoneAutomationExpectedNodeIds.value.length > 0
      && zoneAutomationExpectedNodeIds.value.every((nodeId) => dataFlows.isNodeAttachedToCurrentZone(nodeId))
  })

  const stepGreenhouseClimateDone = computed(() => {
    if (!greenhouseClimateEnabled.value) {
      return true
    }

    return greenhouseClimateBindingsReady.value && greenhouseClimateAppliedAt.value !== null
  })

  const stepZoneDevicesDone = computed(() => {
    return zoneAutomationAssignmentsReady.value
      && zoneAutomationNodesReady.value
  })

  const stepZoneAutomationProfileDone = computed(() => {
    return automationAppliedAt.value !== null
  })

  const stepZoneAutomationDone = computed(() => {
    return stepZoneDevicesDone.value && stepZoneAutomationProfileDone.value
  })

  const stepZoneCalibrationReady = computed(() => {
    return stepZoneAutomationDone.value
  })

  const zoneLaunchReady = computed(() => {
    if (!selectedZoneId.value) {
      return false
    }

    return zoneLaunchReadiness.value?.ready === true
  })

  const zoneLaunchReadinessErrors = computed(() => {
    return Array.isArray(zoneLaunchReadiness.value?.errors)
      ? zoneLaunchReadiness.value?.errors ?? []
      : []
  })

  const launchReadinessSatisfied = computed(() => {
    if (zoneLaunchReady.value) {
      return true
    }

    return automationAppliedAt.value !== null
      && zoneLaunchReadinessErrors.value.length === 0
  })

  const canLaunch = computed(() => {
    return stepZoneDone.value
      && launchReadinessSatisfied.value
      && !selectedZoneHasActiveCycle.value
  })

  const completedSteps = computed(() => {
    return [
      stepGreenhouseDone.value && stepGreenhouseClimateDone.value,
      stepZoneDone.value,
      stepPlantDone.value && stepRecipeDone.value,
      stepZoneAutomationDone.value,
      stepZoneCalibrationReady.value,
      canLaunch.value,
    ].filter(Boolean).length
  })

  const progressPercent = computed(() => Math.min(100, Math.round((completedSteps.value / 6) * 100)))

  const launchChecklist = computed(() => [
    { id: 'zone', label: 'Зона выбрана', done: stepZoneDone.value },
    { id: 'runtime', label: 'Correction runtime готов', done: zoneLaunchReady.value },
    { id: 'cycle', label: 'Нет активного цикла', done: stepZoneDone.value && !selectedZoneHasActiveCycle.value },
  ])

  const stepItems = computed(() => [
    { id: 'greenhouse', title: '1. Теплица', hint: 'Теплица и общий климат', done: stepGreenhouseDone.value && stepGreenhouseClimateDone.value },
    { id: 'zone', title: '2. Зона', hint: 'Рабочая зона выращивания', done: stepZoneDone.value },
    { id: 'plant', title: '3. Культура и рецепт', hint: 'Рецепт подтягивается по выбранной культуре', done: stepPlantDone.value && stepRecipeDone.value },
    { id: 'automation', title: '4. Автоматика зоны', hint: 'Водный контур, климат и освещение как единые блоки', done: stepZoneAutomationDone.value },
    { id: 'calibration', title: '5. Калибровка', hint: 'Сенсоры, насосы и process calibration', done: stepZoneCalibrationReady.value },
    { id: 'launch', title: '6. Проверка и запуск', hint: 'Readiness и мастер цикла', done: canLaunch.value },
  ])

  const waterTopologyLabel = computed(() => {
    if (automationWaterForm.systemType === 'drip') {
      return '2 бака: чистая вода + готовый раствор'
    }

    return '3 бака: чистая вода + раствор + дренаж'
  })

  function deriveZoneAssignmentFromNodes(role: ZoneAssignmentRole, zoneId: number, nodes: Node[]): number | null {
    const zoneNodes = nodes.filter((node) => nodeZoneId(node) === zoneId)
    const expectedBindingRoles = new Set(ZONE_ASSIGNMENT_BINDING_ROLES[role])
    const exactMatch = zoneNodes.find((node) => {
      return nodeBindingRoles(node).some((bindingRole) => expectedBindingRoles.has(bindingRole))
    })

    const exactMatchId = exactMatch ? nodeId(exactMatch) : null
    if (exactMatchId !== null) {
      return exactMatchId
    }

    const fallbackMatches = zoneNodes.filter((node) => matchesZoneAssignmentRole(node, role))
    const fallbackMatchId = fallbackMatches.length === 1 ? nodeId(fallbackMatches[0]) : null
    if (fallbackMatchId !== null) {
      return fallbackMatchId
    }

    return null
  }

  function syncZoneAssignmentsFromAvailableNodes(options?: { preserveManualSelections?: boolean }): void {
    const zoneId = selectedZoneId.value
    const preserveManualSelections = options?.preserveManualSelections ?? true

    if (!zoneId) {
      dataFlows.syncAttachedNodesToCurrentZone([])
      if (!preserveManualSelections) {
        resetZoneAutomationAssignments()
      }
      return
    }

    const zoneNodeIds = availableNodes.value
      .map((node) => ({
        id: nodeId(node),
        zoneId: nodeZoneId(node),
      }))
      .filter((node): node is { id: number; zoneId: number } => node.id !== null && node.zoneId === zoneId)
      .map((node) => node.id)
    dataFlows.syncAttachedNodesToCurrentZone(zoneNodeIds)

    ZONE_ASSIGNMENT_ROLES.forEach((role) => {
      const derivedNodeId = deriveZoneAssignmentFromNodes(role, zoneId, availableNodes.value)
      if (typeof derivedNodeId === 'number') {
        deviceAssignments[role] = derivedNodeId
      } else if (!preserveManualSelections) {
        deviceAssignments[role] = null
      }
    })

    if (typeof deviceAssignments.light === 'number') {
      automationLightingForm.enabled = true
    }

    if (
      typeof deviceAssignments.co2_sensor === 'number'
      || typeof deviceAssignments.co2_actuator === 'number'
      || typeof deviceAssignments.root_vent_actuator === 'number'
    ) {
      zoneClimateForm.enabled = true
    }
  }

  async function refreshAvailableNodes(): Promise<void> {
    await dataFlows.loadAvailableNodes()
    syncZoneAssignmentsFromAvailableNodes({ preserveManualSelections: true })
  }

  async function refreshZoneLaunchReadiness(zoneId: number | null = selectedZoneId.value): Promise<void> {
    if (!zoneId) {
      zoneLaunchReadiness.value = null
      zoneLaunchReadinessLoading.value = false
      return
    }

    zoneLaunchReadinessLoading.value = true

    try {
      const response = await api.get(`/zones/${zoneId}/health`)
      const payload = extractData<ZoneHealthResponse | ZoneLaunchReadiness>(response.data)
      zoneLaunchReadiness.value = (payload as ZoneHealthResponse | null)?.readiness
        ?? (payload as ZoneLaunchReadiness | null)
    } catch {
      zoneLaunchReadiness.value = null
    } finally {
      zoneLaunchReadinessLoading.value = false
    }
  }

  function resetGreenhouseClimateState(): void {
    greenhouseClimateEnabled.value = false
    greenhouseClimateAppliedAt.value = null
    greenhouseClimateBindings.climate_sensors = []
    greenhouseClimateBindings.weather_station_sensors = []
    greenhouseClimateBindings.vent_actuators = []
    greenhouseClimateBindings.fan_actuators = []
  }

  function resetZoneAutomationAssignments(): void {
    deviceAssignments.irrigation = null
    deviceAssignments.ph_correction = null
    deviceAssignments.ec_correction = null
    deviceAssignments.accumulation = null
    deviceAssignments.climate = null
    deviceAssignments.light = null
    deviceAssignments.co2_sensor = null
    deviceAssignments.co2_actuator = null
    deviceAssignments.root_vent_actuator = null
  }

  function formatDateTime(value: string | null): string {
    if (!value) {
      return '-'
    }

    return new Date(value).toLocaleString('ru-RU')
  }

  async function loadGreenhouseClimateProfile(greenhouseId: number | null): Promise<void> {
    resetGreenhouseClimateState()

    if (!greenhouseId) {
      return
    }

    loading.stepGreenhouseClimate = true
    try {
      const response = await automationConfig.getDocument('greenhouse', greenhouseId, GREENHOUSE_LOGIC_PROFILE_NAMESPACE)
      const payload = payloadFromGreenhouseLogicDocument(response)
      const profile = resolveGreenhouseProfileEntry(payload ?? null)
      const bindings = asRecord(payload?.bindings ?? null)

      greenhouseClimateBindings.climate_sensors = toNodeIdArray(bindings?.climate_sensors)
      greenhouseClimateBindings.weather_station_sensors = toNodeIdArray(bindings?.weather_station_sensors)
      greenhouseClimateBindings.vent_actuators = toNodeIdArray(bindings?.vent_actuators)
      greenhouseClimateBindings.fan_actuators = toNodeIdArray(bindings?.fan_actuators)

      if (!profile?.subsystems) {
        return
      }

      const climateSubsystem = asRecord(profile.subsystems.climate ?? null)
      greenhouseClimateEnabled.value = Boolean(climateSubsystem?.enabled ?? false)
      greenhouseClimateAppliedAt.value = typeof profile.updated_at === 'string' ? profile.updated_at : null

      applyAutomationFromRecipe(
        {
          extensions: {
            subsystems: {
              climate: climateSubsystem ?? {},
            },
          },
        },
        {
          climateForm: automationClimateForm,
          waterForm: automationWaterForm,
          lightingForm: automationLightingForm,
          zoneClimateForm,
        }
      )
    } catch {
      showToast('Не удалось загрузить профиль климата теплицы', 'warning')
    } finally {
      loading.stepGreenhouseClimate = false
    }
  }

  function buildGreenhouseClimatePayload(): Record<string, unknown> {
    const payload = buildGrowthCycleConfigPayload(
      {
        climateForm: automationClimateForm,
        waterForm: automationWaterForm,
        lightingForm: automationLightingForm,
        zoneClimateForm,
      },
      {
        includeClimateSubsystem: true,
      }
    )
    const subsystems = asRecord(payload.subsystems ?? null)
    const climate = asRecord(subsystems?.climate ?? null)

    return {
      climate: {
        enabled: greenhouseClimateEnabled.value,
        execution: asRecord(climate?.execution ?? null) ?? {},
      },
    }
  }

  async function applyGreenhouseClimate(): Promise<boolean> {
    if (!canConfigure.value || !selectedGreenhouse.value?.id) {
      return false
    }

    loading.stepGreenhouseClimate = true
    try {
      const bindingsPayload = {
        greenhouse_id: selectedGreenhouse.value.id,
        enabled: greenhouseClimateEnabled.value,
        climate_sensors: [...greenhouseClimateBindings.climate_sensors],
        weather_station_sensors: [...greenhouseClimateBindings.weather_station_sensors],
        vent_actuators: [...greenhouseClimateBindings.vent_actuators],
        fan_actuators: [...greenhouseClimateBindings.fan_actuators],
      }

      if (greenhouseClimateEnabled.value) {
        await api.post('/setup-wizard/validate-greenhouse-climate-devices', bindingsPayload)
      }

      await api.post('/setup-wizard/apply-greenhouse-climate-bindings', bindingsPayload)
      const currentDocument = await automationConfig.getDocument('greenhouse', selectedGreenhouse.value.id, GREENHOUSE_LOGIC_PROFILE_NAMESPACE)
      const currentPayload = payloadFromGreenhouseLogicDocument(currentDocument)
      const response = await automationConfig.updateDocument('greenhouse', selectedGreenhouse.value.id, GREENHOUSE_LOGIC_PROFILE_NAMESPACE, {
        active_mode: 'setup',
        profiles: {
          ...(currentPayload?.profiles ?? {}),
          setup: {
            mode: 'setup',
            is_active: true,
            subsystems: buildGreenhouseClimatePayload(),
            updated_at: new Date().toISOString(),
          },
        },
      })

      const payload = payloadFromGreenhouseLogicDocument(response)
      const profile = resolveGreenhouseProfileEntry(payload ?? null)
      greenhouseClimateAppliedAt.value = typeof profile?.updated_at === 'string' ? profile.updated_at : new Date().toISOString()
      showToast('Профиль климата теплицы сохранён', 'success')
      return true
    } catch {
      showToast('Не удалось сохранить климат теплицы', 'error')
      return false
    } finally {
      loading.stepGreenhouseClimate = false
    }
  }

  function normalizeZoneAssignmentsPayload(
    payload: SetupWizardDeviceAssignments
  ): SetupWizardDeviceAssignments {
    const irrigationId = typeof payload.irrigation === 'number'
      ? payload.irrigation
      : null

    return {
      ...payload,
      accumulation: irrigationId,
      light: automationLightingForm.enabled ? payload.light : null,
      co2_sensor: zoneClimateForm.enabled ? payload.co2_sensor : null,
      co2_actuator: zoneClimateForm.enabled ? payload.co2_actuator : null,
      root_vent_actuator: zoneClimateForm.enabled ? payload.root_vent_actuator : null,
    }
  }

  function buildZoneAssignmentsPayload(): SetupWizardDeviceAssignments {
    return normalizeZoneAssignmentsPayload({
      ...deviceAssignments,
      accumulation: null,
    })
  }

  function buildPartialZoneAssignmentsPayload(
    roles: Array<keyof SetupWizardDeviceAssignments>
  ): SetupWizardDeviceAssignments {
    const payload: SetupWizardDeviceAssignments = {
      irrigation: null,
      ph_correction: null,
      ec_correction: null,
      accumulation: null,
      climate: null,
      light: null,
      co2_sensor: null,
      co2_actuator: null,
      root_vent_actuator: null,
    }

    const normalizedRoles = new Set(roles)
    normalizedRoles.forEach((role) => {
      if (role === 'accumulation' || role === 'climate') {
        return
      }
      payload[role] = deviceAssignments[role]
    })

    return normalizeZoneAssignmentsPayload(payload)
  }

  async function persistZoneDeviceBindings(): Promise<boolean> {
    if (!selectedZone.value?.id) {
      showToast('Сначала выберите зону для привязки устройств.', 'warning')
      return false
    }

    if (
      deviceAssignments.irrigation === null
      || deviceAssignments.ph_correction === null
      || deviceAssignments.ec_correction === null
    ) {
      showToast('Сначала выберите обязательные устройства зоны: полив, pH и EC.', 'warning')
      return false
    }

    loading.stepDevices = true
    try {
      const payload = buildZoneAssignmentsPayload()
      const selectedNodeIdsPayload = zoneAutomationExpectedNodeIds.value

      await api.post('/setup-wizard/validate-devices', {
        zone_id: selectedZone.value.id,
        assignments: payload,
        selected_node_ids: selectedNodeIdsPayload,
      })

      await api.post('/setup-wizard/apply-device-bindings', {
        zone_id: selectedZone.value.id,
        assignments: payload,
        selected_node_ids: selectedNodeIdsPayload,
      })

      showToast('Bindings устройств зоны сохранены', 'success')
      return true
    } catch {
      showToast('Не удалось сохранить bindings устройств зоны', 'error')
      return false
    } finally {
      loading.stepDevices = false
    }
  }

  async function saveZoneDeviceBindingsSection(
    roles: Array<keyof SetupWizardDeviceAssignments>
  ): Promise<boolean> {
    if (!selectedZone.value?.id) {
      showToast('Сначала выберите зону для привязки устройств.', 'warning')
      return false
    }

    const payload = buildPartialZoneAssignmentsPayload(roles)
    const nodeIds = Array.from(new Set(
      roles
        .map((role) => payload[role])
        .filter((value): value is number => typeof value === 'number' && Number.isInteger(value) && value > 0)
    ))

    if (nodeIds.length > 0) {
      selectedNodeIds.value = nodeIds
      await dataFlows.attachNodesToZone(null)
    }

    return await persistZoneDeviceBindings()
  }

  async function attachZoneDevicesOnly(
    roles: Array<keyof SetupWizardDeviceAssignments>
  ): Promise<boolean> {
    if (!selectedZone.value?.id) {
      showToast('Сначала выберите зону для привязки устройств.', 'warning')
      return false
    }

    const payload = buildPartialZoneAssignmentsPayload(roles)
    const nodeIds = Array.from(new Set(
      roles
        .map((role) => payload[role])
        .filter((value): value is number => typeof value === 'number' && Number.isInteger(value) && value > 0)
    ))

    if (nodeIds.length === 0) {
      showToast('Сначала выберите ноду для привязки.', 'warning')
      return false
    }

    selectedNodeIds.value = nodeIds
    await dataFlows.attachNodesToZone(payload)

    const confirmedNodeIds = nodeIds.filter((nodeId) => dataFlows.isNodeAttachedToCurrentZone(nodeId))
    if (confirmedNodeIds.length === nodeIds.length) {
      showToast('Выбранные ноды успешно привязаны к зоне.', 'success')
      return true
    }

    showToast('Привязка отправлена, но не все выбранные ноды ещё подтвердили binding.', 'warning')
    return false
  }

  async function createGreenhouseAndSelectMode(): Promise<void> {
    const previousGreenhouseId = selectedGreenhouseId.value
    await dataFlows.createGreenhouse()

    if (selectedGreenhouseId.value && selectedGreenhouseId.value !== previousGreenhouseId) {
      greenhouseMode.value = 'select'
      await loadGreenhouseClimateProfile(selectedGreenhouseId.value)
      await dataFlows.loadZones(selectedGreenhouseId.value)
    }
  }

  async function createZoneAndSelectMode(): Promise<void> {
    const previousZoneId = selectedZoneId.value
    await dataFlows.createZone()

    if (selectedZoneId.value && selectedZoneId.value !== previousZoneId) {
      zoneMode.value = 'select'
      resetZoneAutomationAssignments()
      await refreshAvailableNodes()
      syncZoneAssignmentsFromAvailableNodes({ preserveManualSelections: false })
      await refreshZoneLaunchReadiness(selectedZoneId.value)
    }
  }

  async function selectZoneAndRefresh(): Promise<void> {
    await dataFlows.selectZone()

    if (!selectedZoneId.value) {
      return
    }

    await refreshAvailableNodes()
    syncZoneAssignmentsFromAvailableNodes({ preserveManualSelections: false })
    await refreshZoneLaunchReadiness(selectedZoneId.value)
  }

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

  watch(selectedGreenhouseId, async (greenhouseId, previousGreenhouseId) => {
    if (greenhouseId === previousGreenhouseId) {
      return
    }

    selectedZoneId.value = null
    selectedZone.value = null
    selectedNodeIds.value = []
    attachedNodesCount.value = 0
    automationAppliedAt.value = null
    resetZoneAutomationAssignments()
    resetGreenhouseClimateState()

    if (!greenhouseId || greenhouseMode.value !== 'select') {
      availableZones.value = []
      greenhouseClimateNodes.value = []
      return
    }

    zoneMode.value = 'select'
    await Promise.all([
      dataFlows.loadZones(greenhouseId),
      dataFlows.loadGreenhouseClimateNodes({ greenhouseId, includeUnassigned: true }),
      loadGreenhouseClimateProfile(greenhouseId),
    ])
  })

  watch(selectedZoneId, async (zoneId, previousZoneId) => {
    if (zoneId === previousZoneId) {
      return
    }

    if (selectedZone.value?.id && selectedZone.value.id !== zoneId) {
      selectedZone.value = null
    }

    selectedNodeIds.value = []
    attachedNodesCount.value = 0
    automationAppliedAt.value = null
    resetZoneAutomationAssignments()

    if (!zoneId) {
      await refreshAvailableNodes()
      await refreshZoneLaunchReadiness(null)
      return
    }

    await refreshAvailableNodes()
    syncZoneAssignmentsFromAvailableNodes({ preserveManualSelections: false })
    await refreshZoneLaunchReadiness(zoneId)
  })

  watch(
    () => automationWaterForm.systemType,
    (type) => {
      syncSystemToTankLayout(automationWaterForm, type)
      if (type === 'drip') {
        automationWaterForm.drainTargetPercent = 0
      } else if (automationWaterForm.drainTargetPercent <= 0) {
        automationWaterForm.drainTargetPercent = 20
      }
    }
  )

  onMounted(async () => {
    await Promise.all([
      dataFlows.loadGreenhouseTypes(),
      dataFlows.loadGreenhouses(),
      dataFlows.loadPlants(),
      dataFlows.loadRecipes(),
      refreshAvailableNodes(),
    ])

    if (!greenhouseForm.greenhouse_type_id && availableGreenhouseTypes.value.length > 0) {
      greenhouseForm.greenhouse_type_id = availableGreenhouseTypes.value[0].id
    }
  })

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
    greenhouseClimateNodes,
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
    automationClimateForm,
    automationWaterForm,
    automationLightingForm,
    greenhouseClimateEnabled,
    greenhouseClimateBindings,
    greenhouseClimateAppliedAt,
    zoneClimateForm,
    deviceAssignments,
    automationAppliedAt,
    stepGreenhouseDone,
    stepGreenhouseClimateDone,
    stepZoneDone,
    stepPlantDone,
    stepRecipeDone,
    stepZoneDevicesDone,
    stepZoneAutomationProfileDone,
    stepZoneAutomationDone,
    stepZoneCalibrationReady,
    zoneAutomationAssignmentsReady,
    zoneAutomationNodesReady,
    zoneAutomationExpectedNodeIds,
    greenhouseClimateBindingsReady,
    selectedZoneActiveCycleStatus,
    selectedZoneHasActiveCycle,
    zoneLaunchReadiness,
    zoneLaunchReadinessLoading,
    zoneLaunchReadinessErrors,
    zoneLaunchReady,
    launchBlockedReason,
    completedSteps,
    progressPercent,
    canLaunch,
    launchChecklist,
    stepItems,
    waterTopologyLabel,
    generatedGreenhouseUid,
    generatedZoneUid,
    attachZoneDevicesOnly,
    addRecipePhase: recipeAutomationFlows.addRecipePhase,
    createGreenhouse: createGreenhouseAndSelectMode,
    selectGreenhouse: dataFlows.selectGreenhouse,
    createZone: createZoneAndSelectMode,
    selectZone: selectZoneAndRefresh,
    createPlant: dataFlows.createPlant,
    selectPlant: dataFlows.selectPlant,
    createRecipe: recipeAutomationFlows.createRecipe,
    selectRecipe: recipeAutomationFlows.selectRecipe,
    attachNodesToZone: dataFlows.attachNodesToZone,
    isNodeAttachedToCurrentZone: dataFlows.isNodeAttachedToCurrentZone,
    refreshAvailableNodes,
    refreshZoneLaunchReadiness,
    applyGreenhouseClimate,
    saveZoneDeviceBindingsSection,
    applyAutomation: recipeAutomationFlows.applyAutomation,
    openCycleWizard: recipeAutomationFlows.openCycleWizard,
    formatDateTime,
  }
}
