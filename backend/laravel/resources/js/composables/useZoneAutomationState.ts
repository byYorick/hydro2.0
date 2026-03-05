import { computed, reactive, ref, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'
import {
  applyAutomationFromRecipe,
  clamp,
  resetToRecommended as resetFormsToRecommended,
  syncSystemToTankLayout,
  type ClimateFormState,
  type IrrigationSystem,
  type LightingFormState,
  type WaterFormState,
} from '@/composables/zoneAutomationFormLogic'
import {
  toFiniteNumber,
  normalizeAutomationLogicMode,
  parseIsoDate,
  type AutomationLogicMode,
} from '@/composables/zoneAutomationUtils'
import type { PredictionTargets, ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import type { ToastVariant } from '@/composables/useToast'

// ─── Private sanitize helpers ─────────────────────────────────────────────────

function toBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1' || value === 'true') return true
  if (value === 0 || value === '0' || value === 'false') return false
  return fallback
}

function toNumber(value: unknown, fallback: number): number {
  const parsed = toFiniteNumber(value)
  return parsed === null ? fallback : parsed
}

function toRoundedNumber(value: unknown, fallback: number): number {
  return Math.round(toNumber(value, fallback))
}

function toTimeHHmm(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback
  const match = value.trim().match(/^(\d{1,2}):(\d{2})/)
  if (!match) return fallback
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (
    !Number.isInteger(hours) ||
    !Number.isInteger(minutes) ||
    hours < 0 ||
    hours > 23 ||
    minutes < 0 ||
    minutes > 59
  ) {
    return fallback
  }
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

function toIrrigationSystem(value: unknown, fallback: IrrigationSystem): IrrigationSystem {
  if (value === 'drip' || value === 'substrate_trays' || value === 'nft') {
    return value
  }
  return fallback
}

function sanitizeClimateForm(raw: Partial<ClimateFormState> | undefined, fallback: ClimateFormState): ClimateFormState {
  return {
    enabled: toBoolean(raw?.enabled, fallback.enabled),
    dayTemp: clamp(toNumber(raw?.dayTemp, fallback.dayTemp), 10, 35),
    nightTemp: clamp(toNumber(raw?.nightTemp, fallback.nightTemp), 10, 35),
    dayHumidity: clamp(toNumber(raw?.dayHumidity, fallback.dayHumidity), 30, 90),
    nightHumidity: clamp(toNumber(raw?.nightHumidity, fallback.nightHumidity), 30, 90),
    intervalMinutes: clamp(toRoundedNumber(raw?.intervalMinutes, fallback.intervalMinutes), 1, 1440),
    dayStart: toTimeHHmm(raw?.dayStart, fallback.dayStart),
    nightStart: toTimeHHmm(raw?.nightStart, fallback.nightStart),
    ventMinPercent: clamp(toRoundedNumber(raw?.ventMinPercent, fallback.ventMinPercent), 0, 100),
    ventMaxPercent: clamp(toRoundedNumber(raw?.ventMaxPercent, fallback.ventMaxPercent), 0, 100),
    useExternalTelemetry: toBoolean(raw?.useExternalTelemetry, fallback.useExternalTelemetry),
    outsideTempMin: clamp(toNumber(raw?.outsideTempMin, fallback.outsideTempMin), -30, 45),
    outsideTempMax: clamp(toNumber(raw?.outsideTempMax, fallback.outsideTempMax), -30, 45),
    outsideHumidityMax: clamp(toRoundedNumber(raw?.outsideHumidityMax, fallback.outsideHumidityMax), 20, 100),
    manualOverrideEnabled: toBoolean(raw?.manualOverrideEnabled, fallback.manualOverrideEnabled),
    overrideMinutes: clamp(toRoundedNumber(raw?.overrideMinutes, fallback.overrideMinutes), 5, 120),
  }
}

function sanitizeWaterForm(raw: Partial<WaterFormState> | undefined, fallback: WaterFormState): WaterFormState {
  const systemType = toIrrigationSystem(raw?.systemType, fallback.systemType)
  const tanksRaw = toRoundedNumber(raw?.tanksCount, fallback.tanksCount)
  const tanksCount = tanksRaw === 3 ? 3 : 2

  const sanitized: WaterFormState = {
    systemType,
    tanksCount,
    cleanTankFillL: clamp(toRoundedNumber(raw?.cleanTankFillL, fallback.cleanTankFillL), 10, 5000),
    nutrientTankTargetL: clamp(toRoundedNumber(raw?.nutrientTankTargetL, fallback.nutrientTankTargetL), 10, 5000),
    irrigationBatchL: clamp(toRoundedNumber(raw?.irrigationBatchL, fallback.irrigationBatchL), 1, 500),
    intervalMinutes: clamp(toRoundedNumber(raw?.intervalMinutes, fallback.intervalMinutes), 5, 1440),
    durationSeconds: clamp(toRoundedNumber(raw?.durationSeconds, fallback.durationSeconds), 1, 3600),
    fillTemperatureC: clamp(toNumber(raw?.fillTemperatureC, fallback.fillTemperatureC), 5, 35),
    fillWindowStart: toTimeHHmm(raw?.fillWindowStart, fallback.fillWindowStart),
    fillWindowEnd: toTimeHHmm(raw?.fillWindowEnd, fallback.fillWindowEnd),
    targetPh: clamp(toNumber(raw?.targetPh, fallback.targetPh), 4, 9),
    targetEc: clamp(toNumber(raw?.targetEc, fallback.targetEc), 0.1, 10),
    phPct: clamp(toNumber(raw?.phPct, fallback.phPct), 1, 50),
    ecPct: clamp(toNumber(raw?.ecPct, fallback.ecPct), 1, 50),
    valveSwitching: toBoolean(raw?.valveSwitching, fallback.valveSwitching),
    correctionDuringIrrigation: toBoolean(raw?.correctionDuringIrrigation, fallback.correctionDuringIrrigation),
    enableDrainControl: toBoolean(raw?.enableDrainControl, fallback.enableDrainControl),
    drainTargetPercent: clamp(toRoundedNumber(raw?.drainTargetPercent, fallback.drainTargetPercent), 0, 100),
    diagnosticsEnabled: toBoolean(raw?.diagnosticsEnabled, fallback.diagnosticsEnabled),
    diagnosticsIntervalMinutes: clamp(
      toRoundedNumber(raw?.diagnosticsIntervalMinutes, fallback.diagnosticsIntervalMinutes),
      1,
      1440
    ),
    cycleStartWorkflowEnabled: toBoolean(raw?.cycleStartWorkflowEnabled, fallback.cycleStartWorkflowEnabled),
    cleanTankFullThreshold: clamp(toNumber(raw?.cleanTankFullThreshold, fallback.cleanTankFullThreshold), 0.05, 1),
    refillDurationSeconds: clamp(toRoundedNumber(raw?.refillDurationSeconds, fallback.refillDurationSeconds), 1, 3600),
    refillTimeoutSeconds: clamp(toRoundedNumber(raw?.refillTimeoutSeconds, fallback.refillTimeoutSeconds), 30, 86400),
    refillRequiredNodeTypes:
      typeof raw?.refillRequiredNodeTypes === 'string' && raw.refillRequiredNodeTypes.trim() !== ''
        ? raw.refillRequiredNodeTypes.trim()
        : fallback.refillRequiredNodeTypes,
    refillPreferredChannel:
      typeof raw?.refillPreferredChannel === 'string'
        ? raw.refillPreferredChannel.trim()
        : fallback.refillPreferredChannel,
    solutionChangeEnabled: toBoolean(raw?.solutionChangeEnabled, fallback.solutionChangeEnabled),
    solutionChangeIntervalMinutes: clamp(
      toRoundedNumber(raw?.solutionChangeIntervalMinutes, fallback.solutionChangeIntervalMinutes),
      1,
      1440
    ),
    solutionChangeDurationSeconds: clamp(
      toRoundedNumber(raw?.solutionChangeDurationSeconds, fallback.solutionChangeDurationSeconds),
      1,
      86400
    ),
    manualIrrigationSeconds: clamp(
      toRoundedNumber(raw?.manualIrrigationSeconds, fallback.manualIrrigationSeconds),
      1,
      3600
    ),
  }

  syncSystemToTankLayout(sanitized, sanitized.systemType)
  sanitized.tanksCount = sanitized.systemType === 'drip' ? 2 : tanksCount
  if (sanitized.tanksCount === 2) {
    sanitized.enableDrainControl = false
  }
  return sanitized
}

function sanitizeLightingForm(
  raw: Partial<LightingFormState> | undefined,
  fallback: LightingFormState
): LightingFormState {
  return {
    enabled: toBoolean(raw?.enabled, fallback.enabled),
    luxDay: clamp(toRoundedNumber(raw?.luxDay, fallback.luxDay), 0, 120000),
    luxNight: clamp(toRoundedNumber(raw?.luxNight, fallback.luxNight), 0, 120000),
    hoursOn: clamp(toNumber(raw?.hoursOn, fallback.hoursOn), 0, 24),
    intervalMinutes: clamp(toRoundedNumber(raw?.intervalMinutes, fallback.intervalMinutes), 1, 1440),
    scheduleStart: toTimeHHmm(raw?.scheduleStart, fallback.scheduleStart),
    scheduleEnd: toTimeHHmm(raw?.scheduleEnd, fallback.scheduleEnd),
    manualIntensity: clamp(toRoundedNumber(raw?.manualIntensity, fallback.manualIntensity), 0, 100),
    manualDurationHours: clamp(toNumber(raw?.manualDurationHours, fallback.manualDurationHours), 0.5, 24),
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export interface ZoneAutomationStateDeps {
  sendZoneCommand: (zoneId: number, type: string, params?: Record<string, unknown>) => Promise<unknown>
  showToast: (message: string, variant?: ToastVariant) => void
}

export function useZoneAutomationState(props: ZoneAutomationTabProps, deps: ZoneAutomationStateDeps) {
  const page = usePage<{ auth?: { user?: { role?: string } } }>()
  const { sendZoneCommand, showToast } = deps

  // ─── Role / permissions ────────────────────────────────────────────────────
  const role = computed(() => page.props.auth?.user?.role ?? 'viewer')
  const canConfigureAutomation = computed(() => role.value === 'agronomist' || role.value === 'admin')
  const canOperateAutomation = computed(
    () =>
      role.value === 'agronomist' ||
      role.value === 'admin' ||
      role.value === 'operator' ||
      role.value === 'engineer'
  )
  const isSystemTypeLocked = computed(() => {
    const status = String(props.activeGrowCycle?.status ?? '').toUpperCase()
    return status === 'RUNNING' || status === 'PAUSED' || status === 'PLANNED'
  })

  // ─── Forms ─────────────────────────────────────────────────────────────────
  const climateForm = reactive<ClimateFormState>({
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

  const waterForm = reactive<WaterFormState>({
    systemType: 'drip' as IrrigationSystem,
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
    enableDrainControl: false,
    drainTargetPercent: 20,
    diagnosticsEnabled: true,
    diagnosticsIntervalMinutes: 15,
    cycleStartWorkflowEnabled: true,
    cleanTankFullThreshold: 0.95,
    refillDurationSeconds: 30,
    refillTimeoutSeconds: 600,
    refillRequiredNodeTypes: 'irrig,climate,light',
    refillPreferredChannel: 'fill_valve',
    solutionChangeEnabled: false,
    solutionChangeIntervalMinutes: 180,
    solutionChangeDurationSeconds: 120,
    manualIrrigationSeconds: 90,
  })

  const lightingForm = reactive<LightingFormState>({
    enabled: true,
    luxDay: 18000,
    luxNight: 0,
    hoursOn: 16,
    intervalMinutes: 30,
    scheduleStart: '06:00',
    scheduleEnd: '22:00',
    manualIntensity: 75,
    manualDurationHours: 4,
  })

  const quickActions = reactive({
    irrigation: false,
    climate: false,
    lighting: false,
    ph: false,
    ec: false,
  })

  // ─── Flags / refs ──────────────────────────────────────────────────────────
  const isApplyingProfile = ref(false)
  const isHydratingProfile = ref(false)
  const isSyncingAutomationLogicProfile = ref(false)
  const lastAppliedAt = ref<string | null>(null)
  const automationLogicMode = ref<AutomationLogicMode>('working')
  const lastAutomationLogicSyncAt = ref<string | null>(null)
  const pendingTargetsSyncForZoneChange = ref(false)

  // ─── Derived ───────────────────────────────────────────────────────────────
  const predictionTargets = computed<PredictionTargets>(() => {
    const targets = props.targets
    if (!targets || typeof targets !== 'object') return {}

    if ('ph_min' in targets || 'ec_min' in targets || 'temp_min' in targets || 'humidity_min' in targets) {
      const legacy = targets as ZoneTargetsType
      return {
        ph: { min: legacy.ph_min, max: legacy.ph_max },
        ec: { min: legacy.ec_min, max: legacy.ec_max },
        temp_air: { min: legacy.temp_min, max: legacy.temp_max },
        humidity_air: { min: legacy.humidity_min, max: legacy.humidity_max },
      }
    }

    return targets as PredictionTargets
  })

  const telemetryLabel = computed(() => {
    const temperature = toFiniteNumber(props.telemetry?.temperature)
    const humidity = toFiniteNumber(props.telemetry?.humidity)

    if (temperature === null || humidity === null) {
      return 'нет данных'
    }

    return `${temperature.toFixed(1)}°C / ${humidity.toFixed(0)}%`
  })

  const waterTopologyLabel = computed(() => {
    if (waterForm.tanksCount === 2) {
      return 'Чистая вода + раствор'
    }

    return 'Чистая вода + раствор + дренаж'
  })

  const profileStorageKey = computed(() => {
    return props.zoneId ? `zone:${props.zoneId}:automation-profile:v3` : null
  })

  // ─── Storage ───────────────────────────────────────────────────────────────
  function saveProfileToStorage(): void {
    if (isHydratingProfile.value) return
    if (typeof window === 'undefined' || !profileStorageKey.value) return

    const payload = {
      climate: { ...climateForm },
      water: { ...waterForm },
      lighting: { ...lightingForm },
      automationLogicMode: automationLogicMode.value,
      lastAutomationLogicSyncAt: lastAutomationLogicSyncAt.value,
      lastAppliedAt: lastAppliedAt.value,
    }

    try {
      window.localStorage.setItem(profileStorageKey.value, JSON.stringify(payload))
    } catch (error) {
      logger.warn('[ZoneAutomationTab] Failed to save automation profile to storage', { error })
    }
  }

  function loadProfileFromStorage(): void {
    if (typeof window === 'undefined' || !profileStorageKey.value) return

    const raw = window.localStorage.getItem(profileStorageKey.value)
    if (!raw) return

    try {
      const parsed = JSON.parse(raw) as {
        climate?: Partial<ClimateFormState>
        water?: Partial<WaterFormState>
        lighting?: Partial<LightingFormState>
        automationLogicMode?: string
        lastAutomationLogicSyncAt?: string | null
        lastAppliedAt?: string | null
      }

      if (parsed.climate) {
        Object.assign(climateForm, sanitizeClimateForm(parsed.climate, climateForm))
      }
      if (parsed.water) {
        Object.assign(waterForm, sanitizeWaterForm(parsed.water, waterForm))
      }
      if (parsed.lighting) {
        Object.assign(lightingForm, sanitizeLightingForm(parsed.lighting, lightingForm))
      }
      automationLogicMode.value = normalizeAutomationLogicMode(parsed.automationLogicMode, automationLogicMode.value)

      const parsedLastAppliedAt = parseIsoDate(parsed.lastAppliedAt ?? null)
      lastAppliedAt.value = parsedLastAppliedAt ? parsedLastAppliedAt.toISOString() : null
      const parsedSyncedAt = parseIsoDate(parsed.lastAutomationLogicSyncAt ?? null)
      lastAutomationLogicSyncAt.value = parsedSyncedAt ? parsedSyncedAt.toISOString() : null
    } catch (error) {
      logger.warn('[ZoneAutomationTab] Failed to parse stored automation profile', { error })
    }
  }

  // ─── Watchers ──────────────────────────────────────────────────────────────
  watch(
    () => waterForm.systemType,
    (value) => syncSystemToTankLayout(waterForm, value),
    { immediate: true }
  )

  watch(climateForm, saveProfileToStorage, { deep: true })
  watch(waterForm, saveProfileToStorage, { deep: true })
  watch(lightingForm, saveProfileToStorage, { deep: true })
  watch(automationLogicMode, saveProfileToStorage)
  watch(lastAutomationLogicSyncAt, saveProfileToStorage)
  watch(lastAppliedAt, saveProfileToStorage)

  watch(
    () => props.targets,
    (targets) => {
      applyAutomationFromRecipe(targets, { climateForm, waterForm, lightingForm })
      pendingTargetsSyncForZoneChange.value = false
    },
    { deep: true }
  )

  // ─── Quick actions ─────────────────────────────────────────────────────────
  function resetToRecommended(): void {
    resetFormsToRecommended({ climateForm, waterForm, lightingForm })
  }

  async function withQuickAction(key: keyof typeof quickActions, callback: () => Promise<void>): Promise<void> {
    if (quickActions[key]) return

    if (!canOperateAutomation.value) {
      showToast('Команды выполнения доступны оператору и агроному.', 'warning')
      return
    }

    quickActions[key] = true
    try {
      await callback()
    } catch (error) {
      logger.error('[ZoneAutomationTab] Quick action failed', { key, error })
    } finally {
      quickActions[key] = false
    }
  }

  async function runManualIrrigation(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('irrigation', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_IRRIGATION', {
        duration_sec: clamp(Math.round(waterForm.manualIrrigationSeconds), 1, 3600),
      })
    })
  }

  async function runManualClimate(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('climate', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_CLIMATE', {
        target_temp: clamp(climateForm.dayTemp, 10, 35),
        target_humidity: clamp(climateForm.dayHumidity, 30, 90),
      })
    })
  }

  async function runManualLighting(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('lighting', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_LIGHTING', {
        intensity: clamp(Math.round(lightingForm.manualIntensity), 0, 100),
        duration_hours: clamp(lightingForm.manualDurationHours, 0.5, 24),
      })
    })
  }

  async function runManualPh(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('ph', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_PH_CONTROL', {
        target_ph: clamp(waterForm.targetPh, 4, 9),
      })
    })
  }

  async function runManualEc(): Promise<void> {
    if (!props.zoneId) return

    await withQuickAction('ec', async () => {
      await sendZoneCommand(props.zoneId as number, 'FORCE_EC_CONTROL', {
        target_ec: clamp(waterForm.targetEc, 0.1, 10),
      })
    })
  }

  return {
    // Role
    role,
    canConfigureAutomation,
    canOperateAutomation,
    isSystemTypeLocked,
    // Forms
    climateForm,
    waterForm,
    lightingForm,
    quickActions,
    // Flags (public)
    isApplyingProfile,
    isHydratingProfile,
    isSyncingAutomationLogicProfile,
    lastAppliedAt,
    automationLogicMode,
    lastAutomationLogicSyncAt,
    // Internal coordination flag (not part of public composable API)
    pendingTargetsSyncForZoneChange,
    // Derived
    predictionTargets,
    telemetryLabel,
    waterTopologyLabel,
    // Storage (internal, needed by api)
    loadProfileFromStorage,
    saveProfileToStorage,
    profileStorageKey,
    // Actions
    resetToRecommended,
    runManualIrrigation,
    runManualClimate,
    runManualLighting,
    runManualPh,
    runManualEc,
  }
}
