import type { Recipe, RecipePhase, NutrientProduct } from '@/types'
import { resolveRecipePhaseSystemType } from '@/composables/recipeSystemType'

export type RecipeIrrigationMode = 'SUBSTRATE' | 'RECIRC'
export type RecipeSystemType = 'drip' | 'drip_tape' | 'drip_emitter' | 'ebb_flow' | 'nft' | 'dwc' | 'aeroponics'

export interface RecipePhaseDayNightState {
  ph: { day: number | null; night: number | null; night_min: number | null; night_max: number | null }
  ec: { day: number | null; night: number | null; night_min: number | null; night_max: number | null }
  temperature: { day: number | null; night: number | null }
  humidity: { day: number | null; night: number | null }
  soil_moisture: { day: number | null; night: number | null }
  lighting: { day_start_time: string; day_hours: number | null }
}

export interface RecipePhaseFormState {
  id?: number
  stage_template_id: number | null
  phase_index: number
  name: string
  duration_hours: number
  ph_target: number
  ph_min: number
  ph_max: number
  ec_target: number
  ec_min: number
  ec_max: number
  temp_air_target: number | null
  humidity_target: number | null
  lighting_photoperiod_hours: number | null
  lighting_start_time: string
  irrigation_mode: RecipeIrrigationMode
  irrigation_system_type: RecipeSystemType
  substrate_type: string | null
  irrigation_interval_sec: number | null
  irrigation_duration_sec: number | null
  nutrient_program_code: string | null
  nutrient_mode: 'ratio_ec_pid' | 'delta_ec_by_k' | 'dose_ml_l_only'
  nutrient_ec_dosing_mode: 'sequential' | 'parallel'
  nutrient_npk_ratio_pct: number | null
  nutrient_calcium_ratio_pct: number | null
  nutrient_magnesium_ratio_pct: number | null
  nutrient_micro_ratio_pct: number | null
  nutrient_npk_dose_ml_l: number | null
  nutrient_calcium_dose_ml_l: number | null
  nutrient_magnesium_dose_ml_l: number | null
  nutrient_micro_dose_ml_l: number | null
  nutrient_npk_product_id: number | null
  nutrient_calcium_product_id: number | null
  nutrient_magnesium_product_id: number | null
  nutrient_micro_product_id: number | null
  nutrient_dose_delay_sec: number | null
  nutrient_ec_stop_tolerance: number | null
  nutrient_solution_volume_l: number | null
  day_night_enabled: boolean
  day_night: RecipePhaseDayNightState
}

export interface RecipeEditorFormState {
  id: number | null
  name: string
  description: string
  plant_id: number | null
  draft_revision_id: number | null
  phases: RecipePhaseFormState[]
}

export interface PlantOption {
  id: number
  name: string
}

const DEFAULT_NUTRIENT_PROGRAM_CODE = 'YARAREGA_CALCINIT_HAIFA_MICRO_V1'
const DEFAULT_NUTRIENT_DOSE_DELAY_SEC = 12
const DEFAULT_NUTRIENT_EC_STOP_TOLERANCE = 0.07

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

export function toNullableNumber(value: unknown, fallback: number | null = null): number | null {
  if (value === null || value === undefined || value === '') {
    return fallback
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function toNullableInt(value: unknown, fallback: number | null = null): number | null {
  const parsed = toNullableNumber(value, fallback)
  if (parsed === null) {
    return null
  }

  return Math.round(parsed)
}

export function normalizeTimeString(value: unknown, fallback = '06:00:00'): string {
  const normalized = String(value ?? '').trim()
  if (/^\d{2}:\d{2}:\d{2}$/.test(normalized)) {
    return normalized
  }

  if (/^\d{2}:\d{2}$/.test(normalized)) {
    return `${normalized}:00`
  }

  return fallback
}

function resolveIrrigationMode(systemType: RecipeSystemType, rawMode: unknown): RecipeIrrigationMode {
  const normalizedMode = String(rawMode ?? '').trim().toUpperCase()
  if (normalizedMode === 'RECIRC') {
    return 'RECIRC'
  }

  if (normalizedMode === 'SUBSTRATE') {
    return 'SUBSTRATE'
  }

  return systemType === 'nft' ? 'RECIRC' : 'SUBSTRATE'
}

function emptyDayNight(baseLightHours: number | null, baseStartTime: string): RecipePhaseDayNightState {
  return {
    ph: { day: 5.8, night: 5.8, night_min: 5.7, night_max: 5.9 },
    ec: { day: 1.4, night: 1.4, night_min: 1.3, night_max: 1.5 },
    temperature: { day: 23, night: 21 },
    humidity: { day: 60, night: 65 },
    soil_moisture: { day: 45, night: 45 },
    lighting: {
      day_start_time: baseStartTime,
      day_hours: baseLightHours,
    },
  }
}

export function createDefaultRecipePhase(phaseIndex: number): RecipePhaseFormState {
  return {
    stage_template_id: null,
    phase_index: phaseIndex,
    name: `Фаза ${phaseIndex + 1}`,
    duration_hours: 72,
    ph_target: 5.8,
    ph_min: 5.6,
    ph_max: 6.0,
    ec_target: 1.4,
    ec_min: 1.2,
    ec_max: 1.6,
    temp_air_target: 23,
    humidity_target: 62,
    lighting_photoperiod_hours: 16,
    lighting_start_time: '06:00:00',
    irrigation_mode: 'SUBSTRATE',
    irrigation_system_type: 'drip_tape',
    substrate_type: null,
    irrigation_interval_sec: 900,
    irrigation_duration_sec: 15,
    nutrient_program_code: DEFAULT_NUTRIENT_PROGRAM_CODE,
    nutrient_mode: 'ratio_ec_pid',
    nutrient_ec_dosing_mode: 'sequential',
    nutrient_npk_ratio_pct: 44,
    nutrient_calcium_ratio_pct: 36,
    nutrient_magnesium_ratio_pct: 17,
    nutrient_micro_ratio_pct: 3,
    nutrient_npk_dose_ml_l: 0.55,
    nutrient_calcium_dose_ml_l: 0.55,
    nutrient_magnesium_dose_ml_l: 0.25,
    nutrient_micro_dose_ml_l: 0.09,
    nutrient_npk_product_id: null,
    nutrient_calcium_product_id: null,
    nutrient_magnesium_product_id: null,
    nutrient_micro_product_id: null,
    nutrient_dose_delay_sec: DEFAULT_NUTRIENT_DOSE_DELAY_SEC,
    nutrient_ec_stop_tolerance: DEFAULT_NUTRIENT_EC_STOP_TOLERANCE,
    nutrient_solution_volume_l: null,
    day_night_enabled: false,
    day_night: {
      ph: { day: 5.8, night: 5.7, night_min: 5.6, night_max: 5.8 },
      ec: { day: 1.6, night: 1.4, night_min: 1.3, night_max: 1.5 },
      temperature: { day: 23, night: 20 },
      humidity: { day: 62, night: 66 },
      soil_moisture: { day: 45, night: 45 },
      lighting: {
        day_start_time: '06:00:00',
        day_hours: 16,
      },
    },
  }
}

export function hydrateRecipePhaseForm(phase: Partial<RecipePhase> | null | undefined): RecipePhaseFormState {
  const base = createDefaultRecipePhase(Number(phase?.phase_index ?? 0))
  const extensions = asRecord(phase?.extensions)
  const dayNight = asRecord(extensions?.day_night)
  const lighting = asRecord(dayNight?.lighting)
  const soilMoisture = asRecord(dayNight?.soil_moisture)
  const coreSystemType = (['drip', 'substrate_trays', 'nft'] as const).includes(base.irrigation_system_type as never)
    ? (base.irrigation_system_type as 'drip' | 'substrate_trays' | 'nft')
    : 'drip'
  const resolvedSystemType = resolveRecipePhaseSystemType(phase ?? null, coreSystemType)
  const rawPhaseSystem = typeof phase?.irrigation_system_type === 'string' ? phase.irrigation_system_type : null
  const VALID_SYSTEM_TYPES = ['drip', 'drip_tape', 'drip_emitter', 'ebb_flow', 'nft', 'dwc', 'aeroponics'] as const
  // substrate_trays (легаси) маппится на drip_tape по смыслу — проливной с субстратом
  const mappedResolved: RecipeSystemType = resolvedSystemType === 'substrate_trays' ? 'drip_tape' : resolvedSystemType
  const systemType: RecipeSystemType = rawPhaseSystem && VALID_SYSTEM_TYPES.includes(rawPhaseSystem as never)
    ? (rawPhaseSystem as RecipeSystemType)
    : mappedResolved
  const phMin = toNullableNumber(phase?.ph_min ?? phase?.targets?.ph?.min, base.ph_min) ?? base.ph_min
  const phMax = toNullableNumber(phase?.ph_max ?? phase?.targets?.ph?.max, base.ph_max) ?? base.ph_max
  const ecMin = toNullableNumber(phase?.ec_min ?? phase?.targets?.ec?.min, base.ec_min) ?? base.ec_min
  const ecMax = toNullableNumber(phase?.ec_max ?? phase?.targets?.ec?.max, base.ec_max) ?? base.ec_max
  const phTarget = toNullableNumber(
    phase?.ph_target ?? phase?.targets?.ph?.target,
    roundRatio((phMin + phMax) / 2),
  ) ?? base.ph_target
  const ecTarget = toNullableNumber(
    phase?.ec_target ?? phase?.targets?.ec?.target,
    roundRatio((ecMin + ecMax) / 2),
  ) ?? base.ec_target
  const tempAir = toNullableNumber(phase?.temp_air_target ?? phase?.targets?.temp_air, base.temp_air_target)
  const humidityAir = toNullableNumber(phase?.humidity_target ?? phase?.targets?.humidity_air, base.humidity_target)
  const lightHours = toNullableNumber(phase?.lighting_photoperiod_hours ?? phase?.targets?.light_hours, base.lighting_photoperiod_hours)
  const lightingStartTime = normalizeTimeString(phase?.lighting_start_time, base.lighting_start_time)

  const result: RecipePhaseFormState = {
    ...base,
    id: typeof phase?.id === 'number' ? phase.id : undefined,
    stage_template_id: toNullableInt(phase?.stage_template_id),
    phase_index: Number(phase?.phase_index ?? base.phase_index),
    name: String(phase?.name ?? base.name),
    duration_hours: toNullableInt(phase?.duration_hours, base.duration_hours) ?? base.duration_hours,
    ph_target: phTarget,
    ph_min: phMin,
    ph_max: phMax,
    ec_target: ecTarget,
    ec_min: ecMin,
    ec_max: ecMax,
    temp_air_target: tempAir,
    humidity_target: humidityAir,
    lighting_photoperiod_hours: lightHours,
    lighting_start_time: lightingStartTime,
    irrigation_mode: resolveIrrigationMode(systemType, phase?.irrigation_mode),
    irrigation_system_type: systemType,
    substrate_type: typeof phase?.substrate_type === 'string' ? phase.substrate_type : null,
    irrigation_interval_sec: toNullableInt(phase?.irrigation_interval_sec ?? phase?.targets?.irrigation_interval_sec, base.irrigation_interval_sec),
    irrigation_duration_sec: toNullableInt(phase?.irrigation_duration_sec ?? phase?.targets?.irrigation_duration_sec, base.irrigation_duration_sec),
    nutrient_program_code: typeof phase?.nutrient_program_code === 'string' && phase.nutrient_program_code.trim().length > 0
      ? phase.nutrient_program_code
      : base.nutrient_program_code,
    nutrient_mode: phase?.nutrient_mode === 'delta_ec_by_k' || phase?.nutrient_mode === 'dose_ml_l_only'
      ? phase.nutrient_mode
      : 'ratio_ec_pid',
    nutrient_ec_dosing_mode: phase?.nutrient_ec_dosing_mode === 'parallel' ? 'parallel' : 'sequential',
    nutrient_npk_ratio_pct: toNullableNumber(phase?.nutrient_npk_ratio_pct, base.nutrient_npk_ratio_pct),
    nutrient_calcium_ratio_pct: toNullableNumber(phase?.nutrient_calcium_ratio_pct, base.nutrient_calcium_ratio_pct),
    nutrient_magnesium_ratio_pct: toNullableNumber(phase?.nutrient_magnesium_ratio_pct, base.nutrient_magnesium_ratio_pct),
    nutrient_micro_ratio_pct: toNullableNumber(phase?.nutrient_micro_ratio_pct, base.nutrient_micro_ratio_pct),
    nutrient_npk_dose_ml_l: toNullableNumber(phase?.nutrient_npk_dose_ml_l, base.nutrient_npk_dose_ml_l),
    nutrient_calcium_dose_ml_l: toNullableNumber(phase?.nutrient_calcium_dose_ml_l, base.nutrient_calcium_dose_ml_l),
    nutrient_magnesium_dose_ml_l: toNullableNumber(phase?.nutrient_magnesium_dose_ml_l, base.nutrient_magnesium_dose_ml_l),
    nutrient_micro_dose_ml_l: toNullableNumber(phase?.nutrient_micro_dose_ml_l, base.nutrient_micro_dose_ml_l),
    nutrient_npk_product_id: toNullableInt(phase?.nutrient_npk_product_id),
    nutrient_calcium_product_id: toNullableInt(phase?.nutrient_calcium_product_id),
    nutrient_magnesium_product_id: toNullableInt(phase?.nutrient_magnesium_product_id),
    nutrient_micro_product_id: toNullableInt(phase?.nutrient_micro_product_id),
    nutrient_dose_delay_sec: toNullableInt(phase?.nutrient_dose_delay_sec, base.nutrient_dose_delay_sec),
    nutrient_ec_stop_tolerance: toNullableNumber(phase?.nutrient_ec_stop_tolerance, base.nutrient_ec_stop_tolerance),
    nutrient_solution_volume_l: toNullableNumber(phase?.nutrient_solution_volume_l),
    day_night_enabled: typeof phase?.day_night_enabled === 'boolean' ? phase.day_night_enabled : false,
    day_night: emptyDayNight(lightHours, lightingStartTime),
  }

  result.day_night.ph.day = toNullableNumber(asRecord(dayNight?.ph)?.day, result.ph_target)
  result.day_night.ph.night = toNullableNumber(asRecord(dayNight?.ph)?.night, result.ph_target)
  const phNight = result.day_night.ph.night ?? result.ph_target ?? 5.8
  result.day_night.ph.night_min = toNullableNumber(asRecord(dayNight?.ph)?.night_min, +(phNight - 0.1).toFixed(2))
  result.day_night.ph.night_max = toNullableNumber(asRecord(dayNight?.ph)?.night_max, +(phNight + 0.1).toFixed(2))
  result.day_night.ec.day = toNullableNumber(asRecord(dayNight?.ec)?.day, result.ec_target)
  result.day_night.ec.night = toNullableNumber(asRecord(dayNight?.ec)?.night, result.ec_target)
  const ecNight = result.day_night.ec.night ?? result.ec_target ?? 1.4
  result.day_night.ec.night_min = toNullableNumber(asRecord(dayNight?.ec)?.night_min, +(ecNight - 0.1).toFixed(2))
  result.day_night.ec.night_max = toNullableNumber(asRecord(dayNight?.ec)?.night_max, +(ecNight + 0.1).toFixed(2))
  result.day_night.temperature.day = toNullableNumber(asRecord(dayNight?.temperature)?.day, result.temp_air_target)
  result.day_night.temperature.night = toNullableNumber(asRecord(dayNight?.temperature)?.night, result.temp_air_target)
  result.day_night.humidity.day = toNullableNumber(asRecord(dayNight?.humidity)?.day, result.humidity_target)
  result.day_night.humidity.night = toNullableNumber(asRecord(dayNight?.humidity)?.night, result.humidity_target)
  result.day_night.soil_moisture.day = toNullableNumber(soilMoisture?.day, result.day_night.soil_moisture.day)
  result.day_night.soil_moisture.night = toNullableNumber(soilMoisture?.night, result.day_night.soil_moisture.night)
  result.day_night.lighting.day_start_time = normalizeTimeString(lighting?.day_start_time ?? result.lighting_start_time, result.lighting_start_time)
  result.day_night.lighting.day_hours = toNullableNumber(lighting?.day_hours, result.lighting_photoperiod_hours)

  return result
}

export function createRecipeEditorFormState(recipe?: Partial<Recipe> | null): RecipeEditorFormState {
  const plants = Array.isArray(recipe?.plants) ? recipe.plants : []
  return {
    id: typeof recipe?.id === 'number' ? recipe.id : null,
    name: String(recipe?.name ?? ''),
    description: String(recipe?.description ?? ''),
    plant_id: typeof plants?.[0]?.id === 'number' ? plants[0].id : null,
    draft_revision_id: typeof recipe?.draft_revision_id === 'number' ? recipe.draft_revision_id : null,
    phases: Array.isArray(recipe?.phases) && recipe.phases.length > 0
      ? recipe.phases.map((phase) => hydrateRecipePhaseForm(phase))
      : [createDefaultRecipePhase(0)],
  }
}

export interface EcBreakdown {
  npk: number
  calcium: number
  magnesium: number
  micro: number
  total: number
  npkShare: number
}

export function computeEcBreakdown(phase: RecipePhaseFormState): EcBreakdown {
  const ec = phase.ec_target ?? 0
  const npk = toNullableNumber(phase.nutrient_npk_ratio_pct, 0) ?? 0
  const calcium = toNullableNumber(phase.nutrient_calcium_ratio_pct, 0) ?? 0
  const magnesium = toNullableNumber(phase.nutrient_magnesium_ratio_pct, 0) ?? 0
  const micro = toNullableNumber(phase.nutrient_micro_ratio_pct, 0) ?? 0
  const sum = npk + calcium + magnesium + micro
  if (sum <= 0 || ec <= 0) {
    return { npk: 0, calcium: 0, magnesium: 0, micro: 0, total: 0, npkShare: 0 }
  }
  return {
    npk: +(ec * npk / sum).toFixed(3),
    calcium: +(ec * calcium / sum).toFixed(3),
    magnesium: +(ec * magnesium / sum).toFixed(3),
    micro: +(ec * micro / sum).toFixed(3),
    total: ec,
    npkShare: +(npk / sum).toFixed(4),
  }
}

export function nutrientRatioSum(phase: RecipePhaseFormState): number {
  const npk = toNullableNumber(phase.nutrient_npk_ratio_pct, 0) ?? 0
  const calcium = toNullableNumber(phase.nutrient_calcium_ratio_pct, 0) ?? 0
  const magnesium = toNullableNumber(phase.nutrient_magnesium_ratio_pct, 0) ?? 0
  const micro = toNullableNumber(phase.nutrient_micro_ratio_pct, 0) ?? 0
  return npk + calcium + magnesium + micro
}

export function isNutrientRatioValid(phase: RecipePhaseFormState): boolean {
  return Math.abs(nutrientRatioSum(phase) - 100) <= 0.01
}

function roundRatio(value: number): number {
  return Math.round(value * 100) / 100
}

export function normalizePhaseRatios(phase: RecipePhaseFormState): void {
  const npk = toNullableNumber(phase.nutrient_npk_ratio_pct, 0) ?? 0
  const calcium = toNullableNumber(phase.nutrient_calcium_ratio_pct, 0) ?? 0
  const magnesium = toNullableNumber(phase.nutrient_magnesium_ratio_pct, 0) ?? 0
  const micro = toNullableNumber(phase.nutrient_micro_ratio_pct, 0) ?? 0

  const sum = npk + calcium + magnesium + micro
  if (sum <= 0) {
    phase.nutrient_npk_ratio_pct = 44
    phase.nutrient_calcium_ratio_pct = 36
    phase.nutrient_magnesium_ratio_pct = 17
    phase.nutrient_micro_ratio_pct = 3
    return
  }

  const normalizedNpk = roundRatio((npk / sum) * 100)
  const normalizedCalcium = roundRatio((calcium / sum) * 100)
  const normalizedMagnesium = roundRatio((magnesium / sum) * 100)
  let normalizedMicro = roundRatio(100 - normalizedNpk - normalizedCalcium - normalizedMagnesium)

  if (normalizedMicro < 0) {
    normalizedMicro = 0
  }

  const normalizedSum = normalizedNpk + normalizedCalcium + normalizedMagnesium + normalizedMicro
  if (Math.abs(normalizedSum - 100) > 0.01) {
    normalizedMicro = roundRatio(normalizedMicro + (100 - normalizedSum))
  }

  phase.nutrient_npk_ratio_pct = normalizedNpk
  phase.nutrient_calcium_ratio_pct = normalizedCalcium
  phase.nutrient_magnesium_ratio_pct = normalizedMagnesium
  phase.nutrient_micro_ratio_pct = normalizedMicro
}

export function buildRecipePhasePayload(phase: RecipePhaseFormState): Record<string, unknown> {
  return {
    stage_template_id: phase.stage_template_id,
    phase_index: phase.phase_index,
    name: phase.name.trim() || `Фаза ${phase.phase_index + 1}`,
    duration_hours: toNullableInt(phase.duration_hours, 0),
    duration_days: toNullableInt(Math.round((phase.duration_hours / 24) * 100) / 100),
    ph_target: toNullableNumber(phase.ph_target),
    ph_min: toNullableNumber(phase.ph_min),
    ph_max: toNullableNumber(phase.ph_max),
    ec_target: toNullableNumber(phase.ec_target),
    ec_min: toNullableNumber(phase.ec_min),
    ec_max: toNullableNumber(phase.ec_max),
    temp_air_target: toNullableNumber(phase.temp_air_target),
    humidity_target: toNullableNumber(phase.humidity_target),
    lighting_photoperiod_hours: toNullableInt(phase.lighting_photoperiod_hours),
    lighting_start_time: normalizeTimeString(phase.lighting_start_time),
    irrigation_mode: phase.irrigation_mode,
    irrigation_system_type: phase.irrigation_system_type,
    irrigation_interval_sec: toNullableInt(phase.irrigation_interval_sec),
    irrigation_duration_sec: toNullableInt(phase.irrigation_duration_sec),
    substrate_type: phase.substrate_type?.trim() || null,
    day_night_enabled: !!phase.day_night_enabled,
    nutrient_program_code: phase.nutrient_program_code?.trim() || null,
    nutrient_mode: phase.nutrient_mode,
    nutrient_ec_dosing_mode: phase.nutrient_ec_dosing_mode || 'sequential',
    nutrient_npk_ratio_pct: toNullableNumber(phase.nutrient_npk_ratio_pct),
    nutrient_calcium_ratio_pct: toNullableNumber(phase.nutrient_calcium_ratio_pct),
    nutrient_magnesium_ratio_pct: toNullableNumber(phase.nutrient_magnesium_ratio_pct),
    nutrient_micro_ratio_pct: toNullableNumber(phase.nutrient_micro_ratio_pct),
    nutrient_npk_dose_ml_l: toNullableNumber(phase.nutrient_npk_dose_ml_l),
    nutrient_calcium_dose_ml_l: toNullableNumber(phase.nutrient_calcium_dose_ml_l),
    nutrient_magnesium_dose_ml_l: toNullableNumber(phase.nutrient_magnesium_dose_ml_l),
    nutrient_micro_dose_ml_l: toNullableNumber(phase.nutrient_micro_dose_ml_l),
    nutrient_npk_product_id: toNullableInt(phase.nutrient_npk_product_id),
    nutrient_calcium_product_id: toNullableInt(phase.nutrient_calcium_product_id),
    nutrient_magnesium_product_id: toNullableInt(phase.nutrient_magnesium_product_id),
    nutrient_micro_product_id: toNullableInt(phase.nutrient_micro_product_id),
    nutrient_dose_delay_sec: toNullableInt(phase.nutrient_dose_delay_sec),
    nutrient_ec_stop_tolerance: toNullableNumber(phase.nutrient_ec_stop_tolerance),
    nutrient_solution_volume_l: toNullableNumber(phase.nutrient_solution_volume_l),
    extensions: {
      day_night: {
        ph: {
          day: toNullableNumber(phase.day_night.ph.day),
          night: toNullableNumber(phase.day_night.ph.night),
          night_min: toNullableNumber(phase.day_night.ph.night_min),
          night_max: toNullableNumber(phase.day_night.ph.night_max),
        },
        ec: {
          day: toNullableNumber(phase.day_night.ec.day),
          night: toNullableNumber(phase.day_night.ec.night),
          night_min: toNullableNumber(phase.day_night.ec.night_min),
          night_max: toNullableNumber(phase.day_night.ec.night_max),
        },
        temperature: {
          day: toNullableNumber(phase.day_night.temperature.day),
          night: toNullableNumber(phase.day_night.temperature.night),
        },
        humidity: {
          day: toNullableNumber(phase.day_night.humidity.day),
          night: toNullableNumber(phase.day_night.humidity.night),
        },
        soil_moisture: {
          day: toNullableNumber(phase.day_night.soil_moisture.day),
          night: toNullableNumber(phase.day_night.soil_moisture.night),
        },
        lighting: {
          day_start_time: normalizeTimeString(phase.day_night.lighting.day_start_time, phase.lighting_start_time),
          day_hours: toNullableNumber(phase.day_night.lighting.day_hours, phase.lighting_photoperiod_hours),
        },
      },
      subsystems: {
        irrigation: {
          targets: {
            system_type: phase.irrigation_system_type,
          },
        },
      },
    },
  }
}

export function mapSimpleRecipePhaseToForm(phase: {
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
}): RecipePhaseFormState {
  const form = createDefaultRecipePhase(phase.phase_index)
  form.name = phase.name
  form.duration_hours = phase.duration_hours
  form.ph_target = phase.targets.ph
  form.ph_min = phase.targets.ph
  form.ph_max = phase.targets.ph
  form.ec_target = phase.targets.ec
  form.ec_min = phase.targets.ec
  form.ec_max = phase.targets.ec
  form.temp_air_target = phase.targets.temp_air
  form.humidity_target = phase.targets.humidity_air
  form.lighting_photoperiod_hours = phase.targets.light_hours
  form.irrigation_interval_sec = phase.targets.irrigation_interval_sec
  form.irrigation_duration_sec = phase.targets.irrigation_duration_sec
  form.day_night.ph.day = phase.targets.ph
  form.day_night.ph.night = phase.targets.ph
  form.day_night.ec.day = phase.targets.ec
  form.day_night.ec.night = phase.targets.ec
  form.day_night.temperature.day = phase.targets.temp_air
  form.day_night.temperature.night = phase.targets.temp_air
  form.day_night.humidity.day = phase.targets.humidity_air
  form.day_night.humidity.night = phase.targets.humidity_air
  form.day_night.lighting.day_hours = phase.targets.light_hours
  return form
}

function validateBoundedTarget(
  label: string,
  target: number | null,
  min: number | null,
  max: number | null,
): string | null {
  if (target === null || min === null || max === null) {
    return `${label}: заполните target, min и max`
  }

  if (min > max) {
    return `${label}: min не может быть больше max`
  }

  if (target < min || target > max) {
    return `${label}: target должен быть в диапазоне min..max`
  }

  return null
}

export function getRecipePhaseTargetValidationError(phase: RecipePhaseFormState): string | null {
  return validateBoundedTarget(
    'pH',
    toNullableNumber(phase.ph_target),
    toNullableNumber(phase.ph_min),
    toNullableNumber(phase.ph_max),
  ) ?? validateBoundedTarget(
    'EC',
    toNullableNumber(phase.ec_target),
    toNullableNumber(phase.ec_min),
    toNullableNumber(phase.ec_max),
  )
}

export function filterProductsByComponent(products: NutrientProduct[], component: NutrientProduct['component']): NutrientProduct[] {
  return products.filter((product) => product.component === component)
}
