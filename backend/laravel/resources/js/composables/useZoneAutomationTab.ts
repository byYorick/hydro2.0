import { computed, onMounted, reactive, ref, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
import { useCommands } from '@/composables/useCommands'
import { useToast } from '@/composables/useToast'
import { logger } from '@/utils/logger'
import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'
import {
  applyAutomationFromRecipe,
  buildGrowthCycleConfigPayload,
  clamp,
  resetToRecommended as resetFormsToRecommended,
  syncSystemToTankLayout,
  type ClimateFormState,
  type IrrigationSystem,
  type LightingFormState,
  validateForms,
  type WaterFormState,
} from '@/composables/zoneAutomationFormLogic'

export type PredictionTargets = Record<string, { min?: number; max?: number }>

export interface ZoneAutomationTabProps {
  zoneId: number | null
  targets: ZoneTargetsType | PredictionTargets
  telemetry?: ZoneTelemetry | null
}

export function useZoneAutomationTab(props: ZoneAutomationTabProps) {
  const page = usePage<{ auth?: { user?: { role?: string } } }>()
  const { showToast } = useToast()
  const { sendZoneCommand } = useCommands(showToast)

  const role = computed(() => page.props.auth?.user?.role ?? 'viewer')
  const canConfigureAutomation = computed(() => role.value === 'agronomist' || role.value === 'admin')
  const canOperateAutomation = computed(
    () => role.value === 'agronomist' || role.value === 'admin' || role.value === 'operator'
  )

  const climateForm = reactive<ClimateFormState>({
    enabled: true,
    dayTemp: 23,
    nightTemp: 20,
    dayHumidity: 62,
    nightHumidity: 70,
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
    valveSwitching: true,
    correctionDuringIrrigation: true,
    enableDrainControl: false,
    drainTargetPercent: 20,
    manualIrrigationSeconds: 90,
  })

  const lightingForm = reactive<LightingFormState>({
    enabled: true,
    luxDay: 18000,
    luxNight: 0,
    hoursOn: 16,
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

  const isApplyingProfile = ref(false)
  const lastAppliedAt = ref<string | null>(null)

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
    const temperature = props.telemetry?.temperature
    const humidity = props.telemetry?.humidity

    if (temperature === undefined || temperature === null || humidity === undefined || humidity === null) {
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
    return props.zoneId ? `zone:${props.zoneId}:automation-profile:v2` : null
  })

  watch(
    () => waterForm.systemType,
    (value) => syncSystemToTankLayout(waterForm, value),
    { immediate: true }
  )

  function saveProfileToStorage(): void {
    if (typeof window === 'undefined' || !profileStorageKey.value) return

    const payload = {
      climate: { ...climateForm },
      water: { ...waterForm },
      lighting: { ...lightingForm },
      lastAppliedAt: lastAppliedAt.value,
    }

    window.localStorage.setItem(profileStorageKey.value, JSON.stringify(payload))
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
        lastAppliedAt?: string | null
      }

      if (parsed.climate) {
        Object.assign(climateForm, parsed.climate)
      }
      if (parsed.water) {
        Object.assign(waterForm, parsed.water)
        syncSystemToTankLayout(waterForm, waterForm.systemType)
      }
      if (parsed.lighting) {
        Object.assign(lightingForm, parsed.lighting)
      }
      lastAppliedAt.value = parsed.lastAppliedAt ?? null
    } catch (error) {
      logger.warn('[ZoneAutomationTab] Failed to parse stored automation profile', { error })
    }
  }

  watch(climateForm, saveProfileToStorage, { deep: true })
  watch(waterForm, saveProfileToStorage, { deep: true })
  watch(lightingForm, saveProfileToStorage, { deep: true })
  watch(lastAppliedAt, saveProfileToStorage)

  onMounted(() => {
    loadProfileFromStorage()
    applyAutomationFromRecipe(props.targets, { climateForm, waterForm, lightingForm })
  })

  watch(
    () => props.targets,
    (targets) => {
      applyAutomationFromRecipe(targets, { climateForm, waterForm, lightingForm })
    },
    { deep: true }
  )

  async function applyAutomationProfile(): Promise<void> {
    if (!props.zoneId || isApplyingProfile.value) return

    if (!canConfigureAutomation.value) {
      showToast('Изменение профиля доступно только агроному.', 'warning')
      return
    }

    const validationError = validateForms({ climateForm, waterForm })
    if (validationError) {
      showToast(validationError, 'error')
      return
    }

    isApplyingProfile.value = true

    try {
      const payload = buildGrowthCycleConfigPayload({ climateForm, waterForm, lightingForm })
      await sendZoneCommand(props.zoneId, 'GROWTH_CYCLE_CONFIG', payload)
      lastAppliedAt.value = new Date().toISOString()
      showToast('Профиль автоматики отправлен в scheduler.', 'success')
    } catch (error) {
      logger.error('[ZoneAutomationTab] Failed to apply automation profile', { error })
    } finally {
      isApplyingProfile.value = false
    }
  }

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

  function formatDateTime(value: string | null): string {
    if (!value) return '-'
    return new Date(value).toLocaleString('ru-RU')
  }

  return {
    role,
    canConfigureAutomation,
    canOperateAutomation,
    climateForm,
    waterForm,
    lightingForm,
    quickActions,
    isApplyingProfile,
    lastAppliedAt,
    predictionTargets,
    telemetryLabel,
    waterTopologyLabel,
    applyAutomationProfile,
    resetToRecommended,
    runManualIrrigation,
    runManualClimate,
    runManualLighting,
    runManualPh,
    runManualEc,
    formatDateTime,
  }
}
