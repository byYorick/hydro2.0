import { computed, onMounted, reactive, ref, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
import { useCommands } from '@/composables/useCommands'
import { useToast } from '@/composables/useToast'
import { logger } from '@/utils/logger'
import type { ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'

export type PredictionTargets = Record<string, { min?: number; max?: number }>
export type IrrigationSystem = 'drip' | 'substrate_trays' | 'nft'

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
const canOperateAutomation = computed(() => role.value === 'agronomist' || role.value === 'admin' || role.value === 'operator')

const climateForm = reactive({
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

const waterForm = reactive({
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

const lightingForm = reactive({
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

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function normalizeNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  return fallback
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

type Dictionary = Record<string, unknown>

function asRecord(value: unknown): Dictionary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Dictionary
}

function asArray(value: unknown): unknown[] | null {
  if (!Array.isArray(value)) {
    return null
  }

  return value
}

function readNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }

    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) {
        return parsed
      }
    }
  }

  return null
}

function readBoolean(...values: unknown[]): boolean | null {
  for (const value of values) {
    if (typeof value === 'boolean') {
      return value
    }
    if (value === 1 || value === '1' || value === 'true') {
      return true
    }
    if (value === 0 || value === '0' || value === 'false') {
      return false
    }
  }

  return null
}

function readString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim() !== '') {
      return value.trim()
    }
  }

  return null
}

function toTimeHHmm(value: unknown): string | null {
  const raw = readString(value)
  if (!raw) {
    return null
  }

  const match = raw.match(/^(\d{1,2}):(\d{2})/)
  if (!match) {
    return null
  }

  return `${match[1].padStart(2, '0')}:${match[2]}`
}

function asIrrigationSystem(value: unknown): IrrigationSystem | null {
  if (value === 'drip' || value === 'substrate_trays' || value === 'nft') {
    return value
  }

  return null
}

function midpoint(minValue: number | null, maxValue: number | null): number | null {
  if (minValue !== null && maxValue !== null) {
    return (minValue + maxValue) / 2
  }

  return minValue ?? maxValue
}

function applyAutomationFromRecipe(targetsInput: unknown): void {
  const targets = asRecord(targetsInput)
  if (!targets) {
    return
  }

  const extensions = asRecord(targets.extensions)
  const subsystems = asRecord(extensions?.subsystems)
  const irrigationSubsystem = asRecord(subsystems?.irrigation)
  const irrigationTargets = asRecord(irrigationSubsystem?.targets)
  const climateSubsystem = asRecord(subsystems?.climate)
  const climateTargets = asRecord(climateSubsystem?.targets)
  const lightingSubsystem = asRecord(subsystems?.lighting)
  const lightingTargets = asRecord(lightingSubsystem?.targets)

  const phTarget = asRecord(targets.ph)
  const phMin = readNumber(phTarget?.min)
  const phMax = readNumber(phTarget?.max)
  const phValue = readNumber(phTarget?.target, midpoint(phMin, phMax))
  if (phValue !== null) {
    waterForm.targetPh = clamp(phValue, 4, 9)
  }

  const ecTarget = asRecord(targets.ec)
  const ecMin = readNumber(ecTarget?.min)
  const ecMax = readNumber(ecTarget?.max)
  const ecValue = readNumber(ecTarget?.target, midpoint(ecMin, ecMax))
  if (ecValue !== null) {
    waterForm.targetEc = clamp(ecValue, 0.1, 10)
  }

  const irrigation = asRecord(targets.irrigation)
  const intervalSec = readNumber(
    irrigationTargets?.interval_sec,
    irrigationTargets?.interval_seconds,
    irrigation?.interval_sec,
    (targets as Dictionary).irrigation_interval_sec
  )
  if (intervalSec !== null) {
    waterForm.intervalMinutes = clamp(Math.round(intervalSec / 60), 5, 1440)
  }

  const durationSec = readNumber(
    irrigationTargets?.duration_sec,
    irrigationTargets?.duration_seconds,
    irrigation?.duration_sec,
    (targets as Dictionary).irrigation_duration_sec
  )
  if (durationSec !== null) {
    waterForm.durationSeconds = clamp(Math.round(durationSec), 1, 3600)
  }

  const systemType = asIrrigationSystem(readString(irrigationTargets?.system_type))
  if (systemType) {
    waterForm.systemType = systemType
    syncSystemToTankLayout(systemType)
  }

  const tanksCount = readNumber(irrigationTargets?.tanks_count)
  if (tanksCount === 2 || tanksCount === 3) {
    waterForm.tanksCount = tanksCount
    if (tanksCount === 2) {
      waterForm.enableDrainControl = false
    }
  }

  const cleanTankFill = readNumber(irrigationTargets?.clean_tank_fill_l)
  if (cleanTankFill !== null) {
    waterForm.cleanTankFillL = clamp(Math.round(cleanTankFill), 10, 5000)
  }

  const nutrientTankTarget = readNumber(irrigationTargets?.nutrient_tank_target_l)
  if (nutrientTankTarget !== null) {
    waterForm.nutrientTankTargetL = clamp(Math.round(nutrientTankTarget), 10, 5000)
  }

  const irrigationBatch = readNumber(irrigationTargets?.irrigation_batch_l)
  if (irrigationBatch !== null) {
    waterForm.irrigationBatchL = clamp(Math.round(irrigationBatch), 1, 500)
  }

  const fillTemperature = readNumber(irrigationTargets?.fill_temperature_c)
  if (fillTemperature !== null) {
    waterForm.fillTemperatureC = clamp(fillTemperature, 5, 35)
  }

  const irrigationSchedule = asArray(irrigationTargets?.schedule)
  const firstIrrigationWindow = asRecord(irrigationSchedule?.[0])
  const fillStart = toTimeHHmm(firstIrrigationWindow?.start)
  const fillEnd = toTimeHHmm(firstIrrigationWindow?.end)
  if (fillStart) {
    waterForm.fillWindowStart = fillStart
  }
  if (fillEnd) {
    waterForm.fillWindowEnd = fillEnd
  }

  const correctionNode = asRecord(irrigationTargets?.correction_node)
  const correctionPh = readNumber(correctionNode?.target_ph)
  const correctionEc = readNumber(correctionNode?.target_ec)
  if (correctionPh !== null) {
    waterForm.targetPh = clamp(correctionPh, 4, 9)
  }
  if (correctionEc !== null) {
    waterForm.targetEc = clamp(correctionEc, 0.1, 10)
  }

  const valveSwitching = readBoolean(irrigationTargets?.valve_switching_enabled)
  if (valveSwitching !== null) {
    waterForm.valveSwitching = valveSwitching
  }
  const correctionDuringIrrigation = readBoolean(irrigationTargets?.correction_during_irrigation)
  if (correctionDuringIrrigation !== null) {
    waterForm.correctionDuringIrrigation = correctionDuringIrrigation
  }

  const drainControl = asRecord(irrigationTargets?.drain_control)
  const drainEnabled = readBoolean(drainControl?.enabled)
  const drainTarget = readNumber(drainControl?.target_percent)
  if (drainEnabled !== null) {
    waterForm.enableDrainControl = drainEnabled
  }
  if (drainTarget !== null) {
    waterForm.drainTargetPercent = clamp(drainTarget, 0, 100)
  }

  const climateRequest = asRecord(targets.climate_request)
  const climateEnabled = readBoolean(climateSubsystem?.enabled)
  if (climateEnabled !== null) {
    climateForm.enabled = climateEnabled
  }

  const temperature = asRecord(climateTargets?.temperature)
  const humidity = asRecord(climateTargets?.humidity)
  const dayTemp = readNumber(temperature?.day, climateRequest?.temp_air_target)
  const nightTemp = readNumber(temperature?.night, temperature?.day, climateRequest?.temp_air_target)
  const dayHumidity = readNumber(humidity?.day, climateRequest?.humidity_target)
  const nightHumidity = readNumber(humidity?.night, humidity?.day, climateRequest?.humidity_target)
  if (dayTemp !== null) {
    climateForm.dayTemp = clamp(dayTemp, 10, 35)
  }
  if (nightTemp !== null) {
    climateForm.nightTemp = clamp(nightTemp, 10, 35)
  }
  if (dayHumidity !== null) {
    climateForm.dayHumidity = clamp(dayHumidity, 30, 90)
  }
  if (nightHumidity !== null) {
    climateForm.nightHumidity = clamp(nightHumidity, 30, 90)
  }

  const ventControl = asRecord(climateTargets?.vent_control)
  const ventMinPercent = readNumber(ventControl?.min_open_percent)
  const ventMaxPercent = readNumber(ventControl?.max_open_percent)
  if (ventMinPercent !== null) {
    climateForm.ventMinPercent = clamp(Math.round(ventMinPercent), 0, 100)
  }
  if (ventMaxPercent !== null) {
    climateForm.ventMaxPercent = clamp(Math.round(ventMaxPercent), 0, 100)
  }

  const externalGuard = asRecord(climateTargets?.external_guard)
  const externalEnabled = readBoolean(externalGuard?.enabled)
  if (externalEnabled !== null) {
    climateForm.useExternalTelemetry = externalEnabled
  }
  const outsideTempMin = readNumber(externalGuard?.temp_min)
  const outsideTempMax = readNumber(externalGuard?.temp_max)
  const outsideHumidityMax = readNumber(externalGuard?.humidity_max)
  if (outsideTempMin !== null) {
    climateForm.outsideTempMin = clamp(outsideTempMin, -30, 45)
  }
  if (outsideTempMax !== null) {
    climateForm.outsideTempMax = clamp(outsideTempMax, -30, 45)
  }
  if (outsideHumidityMax !== null) {
    climateForm.outsideHumidityMax = clamp(outsideHumidityMax, 20, 100)
  }

  const climateSchedule = asArray(climateTargets?.schedule)
  const daySlot = asRecord(climateSchedule?.find((item) => asRecord(item)?.profile === 'day'))
  const nightSlot = asRecord(climateSchedule?.find((item) => asRecord(item)?.profile === 'night'))
  const dayStart = toTimeHHmm(daySlot?.start)
  const nightStart = toTimeHHmm(nightSlot?.start)
  if (dayStart) {
    climateForm.dayStart = dayStart
  }
  if (nightStart) {
    climateForm.nightStart = nightStart
  }

  const manualOverride = asRecord(climateTargets?.manual_override)
  const manualOverrideEnabled = readBoolean(manualOverride?.enabled)
  const overrideMinutes = readNumber(manualOverride?.timeout_minutes)
  if (manualOverrideEnabled !== null) {
    climateForm.manualOverrideEnabled = manualOverrideEnabled
  }
  if (overrideMinutes !== null) {
    climateForm.overrideMinutes = clamp(Math.round(overrideMinutes), 5, 120)
  }

  const lighting = asRecord(targets.lighting)
  const lightingEnabled = readBoolean(lightingSubsystem?.enabled)
  if (lightingEnabled !== null) {
    lightingForm.enabled = lightingEnabled
  }

  const lux = asRecord(lightingTargets?.lux)
  const luxDay = readNumber(lux?.day)
  const luxNight = readNumber(lux?.night)
  if (luxDay !== null) {
    lightingForm.luxDay = clamp(Math.round(luxDay), 0, 120000)
  }
  if (luxNight !== null) {
    lightingForm.luxNight = clamp(Math.round(luxNight), 0, 120000)
  }

  const photoperiod = asRecord(lightingTargets?.photoperiod)
  const hoursOn = readNumber(photoperiod?.hours_on, lighting?.photoperiod_hours, (targets as Dictionary).light_hours)
  if (hoursOn !== null) {
    lightingForm.hoursOn = clamp(hoursOn, 0, 24)
  }

  const lightingSchedule = asArray(lightingTargets?.schedule)
  const firstLightingWindow = asRecord(lightingSchedule?.[0])
  const scheduleStart = toTimeHHmm(firstLightingWindow?.start ?? lighting?.start_time)
  const scheduleEnd = toTimeHHmm(firstLightingWindow?.end)
  if (scheduleStart) {
    lightingForm.scheduleStart = scheduleStart
  }
  if (scheduleEnd) {
    lightingForm.scheduleEnd = scheduleEnd
  }
}

function syncSystemToTankLayout(systemType: IrrigationSystem): void {
  if (systemType === 'drip') {
    waterForm.tanksCount = 2
    waterForm.enableDrainControl = false
    return
  }

  waterForm.tanksCount = 3
}

watch(
  () => waterForm.systemType,
  (value) => syncSystemToTankLayout(value),
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
      climate?: Partial<typeof climateForm>
      water?: Partial<typeof waterForm>
      lighting?: Partial<typeof lightingForm>
      lastAppliedAt?: string | null
    }

    if (parsed.climate) {
      Object.assign(climateForm, parsed.climate)
    }
    if (parsed.water) {
      Object.assign(waterForm, parsed.water)
      syncSystemToTankLayout(waterForm.systemType)
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
  applyAutomationFromRecipe(props.targets)
})

watch(
  () => props.targets,
  (targets) => {
    applyAutomationFromRecipe(targets)
  },
  { deep: true }
)

function validateForms(): string | null {
  if (climateForm.ventMinPercent > climateForm.ventMaxPercent) {
    return 'Минимум открытия форточек не может быть больше максимума.'
  }

  if (waterForm.cleanTankFillL <= 0 || waterForm.nutrientTankTargetL <= 0) {
    return 'Укажите положительные объёмы баков.'
  }

  if (waterForm.tanksCount === 3 && waterForm.enableDrainControl && waterForm.drainTargetPercent <= 0) {
    return 'Для контроля дренажа задайте целевой процент больше 0.'
  }

  return null
}

function buildGrowthCycleConfigPayload(): Record<string, unknown> {
  const phTarget = clamp(normalizeNumber(waterForm.targetPh, 5.8), 4, 9)
  const ecTarget = clamp(normalizeNumber(waterForm.targetEc, 1.6), 0.1, 10)

  const phMin = round(clamp(phTarget - 0.2, 4, 9), 2)
  const phMax = round(clamp(phTarget + 0.2, 4, 9), 2)
  const ecMin = round(clamp(ecTarget - 0.2, 0.1, 10), 2)
  const ecMax = round(clamp(ecTarget + 0.2, 0.1, 10), 2)

  return {
    mode: 'adjust',
    subsystems: {
      ph: {
        enabled: true,
        targets: {
          min: phMin,
          max: phMax,
          target: round(phTarget, 2),
        },
      },
      ec: {
        enabled: true,
        targets: {
          min: ecMin,
          max: ecMax,
          target: round(ecTarget, 2),
        },
      },
      irrigation: {
        enabled: true,
        targets: {
          interval_minutes: clamp(Math.round(waterForm.intervalMinutes), 5, 1440),
          duration_seconds: clamp(Math.round(waterForm.durationSeconds), 1, 3600),
          system_type: waterForm.systemType,
          tanks_count: waterForm.tanksCount,
          fill_strategy: 'volume',
          correction_strategy: 'feedback_target',
          clean_tank_fill_l: clamp(Math.round(waterForm.cleanTankFillL), 10, 5000),
          nutrient_tank_target_l: clamp(Math.round(waterForm.nutrientTankTargetL), 10, 5000),
          irrigation_batch_l: clamp(Math.round(waterForm.irrigationBatchL), 1, 500),
          valve_switching_enabled: waterForm.valveSwitching,
          correction_during_irrigation: waterForm.correctionDuringIrrigation,
          fill_temperature_c: clamp(waterForm.fillTemperatureC, 5, 35),
          schedule: [
            {
              start: waterForm.fillWindowStart,
              end: waterForm.fillWindowEnd,
              action: 'fill_clean_tank_then_mix',
            },
          ],
          correction_node: {
            target_ph: round(phTarget, 2),
            target_ec: round(ecTarget, 2),
            sensors_location: 'correction_node',
          },
          drain_control: {
            enabled: waterForm.tanksCount === 3 ? waterForm.enableDrainControl : false,
            target_percent: waterForm.tanksCount === 3 ? clamp(waterForm.drainTargetPercent, 0, 100) : null,
          },
        },
      },
      climate: {
        enabled: climateForm.enabled,
        targets: {
          temperature: {
            day: clamp(climateForm.dayTemp, 10, 35),
            night: clamp(climateForm.nightTemp, 10, 35),
          },
          humidity: {
            day: clamp(climateForm.dayHumidity, 30, 90),
            night: clamp(climateForm.nightHumidity, 30, 90),
          },
          vent_control: {
            role: 'vent',
            min_open_percent: clamp(Math.round(climateForm.ventMinPercent), 0, 100),
            max_open_percent: clamp(Math.round(climateForm.ventMaxPercent), 0, 100),
          },
          external_guard: {
            enabled: climateForm.useExternalTelemetry,
            temp_min: climateForm.outsideTempMin,
            temp_max: climateForm.outsideTempMax,
            humidity_max: climateForm.outsideHumidityMax,
          },
          schedule: [
            {
              start: climateForm.dayStart,
              end: climateForm.nightStart,
              profile: 'day',
            },
            {
              start: climateForm.nightStart,
              end: climateForm.dayStart,
              profile: 'night',
            },
          ],
          manual_override: {
            enabled: climateForm.manualOverrideEnabled,
            timeout_minutes: clamp(Math.round(climateForm.overrideMinutes), 5, 120),
          },
        },
      },
      lighting: {
        enabled: lightingForm.enabled,
        targets: {
          lux: {
            day: clamp(Math.round(lightingForm.luxDay), 0, 120000),
            night: clamp(Math.round(lightingForm.luxNight), 0, 120000),
          },
          photoperiod: {
            hours_on: clamp(lightingForm.hoursOn, 0, 24),
            hours_off: round(clamp(24 - lightingForm.hoursOn, 0, 24), 1),
          },
          schedule: [
            {
              start: lightingForm.scheduleStart,
              end: lightingForm.scheduleEnd,
            },
          ],
          future_metrics: {
            ppfd: null,
            dli: null,
            ready: true,
          },
        },
      },
    },
  }
}

async function applyAutomationProfile(): Promise<void> {
  if (!props.zoneId || isApplyingProfile.value) return

  if (!canConfigureAutomation.value) {
    showToast('Изменение профиля доступно только агроному.', 'warning')
    return
  }

  const validationError = validateForms()
  if (validationError) {
    showToast(validationError, 'error')
    return
  }

  isApplyingProfile.value = true

  try {
    const payload = buildGrowthCycleConfigPayload()
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
  climateForm.enabled = true
  climateForm.dayTemp = 23
  climateForm.nightTemp = 20
  climateForm.dayHumidity = 62
  climateForm.nightHumidity = 70
  climateForm.dayStart = '07:00'
  climateForm.nightStart = '19:00'
  climateForm.ventMinPercent = 15
  climateForm.ventMaxPercent = 85
  climateForm.useExternalTelemetry = true
  climateForm.outsideTempMin = 4
  climateForm.outsideTempMax = 34
  climateForm.outsideHumidityMax = 90
  climateForm.manualOverrideEnabled = true
  climateForm.overrideMinutes = 30

  waterForm.systemType = 'drip'
  waterForm.cleanTankFillL = 300
  waterForm.nutrientTankTargetL = 280
  waterForm.irrigationBatchL = 20
  waterForm.intervalMinutes = 30
  waterForm.durationSeconds = 120
  waterForm.fillTemperatureC = 20
  waterForm.fillWindowStart = '05:00'
  waterForm.fillWindowEnd = '07:00'
  waterForm.targetPh = 5.8
  waterForm.targetEc = 1.6
  waterForm.valveSwitching = true
  waterForm.correctionDuringIrrigation = true
  waterForm.enableDrainControl = false
  waterForm.drainTargetPercent = 20
  waterForm.manualIrrigationSeconds = 90

  lightingForm.enabled = true
  lightingForm.luxDay = 18000
  lightingForm.luxNight = 0
  lightingForm.hoursOn = 16
  lightingForm.scheduleStart = '06:00'
  lightingForm.scheduleEnd = '22:00'
  lightingForm.manualIntensity = 75
  lightingForm.manualDurationHours = 4

  syncSystemToTankLayout('drip')
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
