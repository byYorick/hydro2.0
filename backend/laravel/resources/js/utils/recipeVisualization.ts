import type { RecipePhase, RecipePhaseNutrientProduct } from '@/types'

export interface VisualRange {
  target: number | null
  min: number | null
  max: number | null
}

export interface VisualDayNightPair {
  day: number | null
  night: number | null
}

export interface VisualNutritionComponent {
  key: 'npk' | 'calcium' | 'magnesium' | 'micro'
  label: string
  ratioPct: number | null
  doseMlL: number | null
  product: RecipePhaseNutrientProduct | null
  productId: number | null
}

export interface VisualNutrition {
  programCode: string | null
  mode: string | null
  ecDosingMode: string | null
  solutionVolumeL: number | null
  doseDelaySec: number | null
  ecStopTolerance: number | null
  components: VisualNutritionComponent[]
  ratioSum: number
  hasData: boolean
}

export interface VisualDayNight {
  enabled: boolean
  ph: VisualDayNightPair | null
  ec: VisualDayNightPair | null
  temperature: VisualDayNightPair | null
  humidity: VisualDayNightPair | null
  lightingDayHours: number | null
  lightingStartTime: string | null
  hasData: boolean
}

export interface RecipePhaseVisual {
  key: string
  /** Порядковый номер после сортировки: определяет цвет и нумерацию в UI. */
  position: number
  /** Значение phase_index из данных фазы. */
  index: number
  name: string
  stageName: string | null
  durationHours: number | null
  startHours: number
  endHours: number
  startDay: number
  endDay: number
  ph: VisualRange
  ec: VisualRange
  temperature: VisualRange
  humidity: VisualRange
  co2: VisualRange
  dli: VisualRange
  solutionTemp: VisualRange
  lightHours: number | null
  lightStartTime: string | null
  ppfd: number | null
  irrigation: {
    mode: string | null
    systemType: string | null
    substrateType: string | null
    intervalSec: number | null
    durationSec: number | null
  }
  mist: {
    mode: string | null
    intervalSec: number | null
    durationSec: number | null
  }
  nutrition: VisualNutrition
  dayNight: VisualDayNight
  progressModel: string | null
  advanceStrategy: string | null
  targetGdd: number | null
  baseTempC: number | null
  agronomy: {
    criticalControls: string | null
    riskFocus: string | null
  } | null
}

export type RecipeChartMetric =
  | 'ph'
  | 'ec'
  | 'temperature'
  | 'humidity'
  | 'co2'
  | 'dli'
  | 'light'
  | 'solutionTemp'

export interface RecipeVisualSummary {
  phaseCount: number
  totalHours: number | null
  totalDays: number | null
  ph: VisualRange
  ec: VisualRange
  temperature: VisualRange
  humidity: VisualRange
  lightHours: VisualRange
  co2: VisualRange
}

/** Формы фаз из Inertia-props и из состояния редактора отличаются вложенностью day/night. */
export type RecipeVisualPhaseInput = Partial<RecipePhase> & {
  day_night?: unknown
  id?: number | string | null
}

const NUTRITION_LABELS: Record<VisualNutritionComponent['key'], string> = {
  npk: 'NPK',
  calcium: 'Кальций',
  magnesium: 'Магний',
  micro: 'Микро',
}

export const NUTRITION_COLORS: Record<VisualNutritionComponent['key'], string> = {
  npk: 'var(--accent-green)',
  calcium: 'var(--accent-cyan)',
  magnesium: 'var(--accent-amber)',
  micro: 'var(--accent-lime)',
}

const IRRIGATION_SYSTEM_LABELS: Record<string, string> = {
  drip: 'Капельный',
  drip_tape: 'Капельная лента',
  drip_emitter: 'Капельницы',
  substrate_trays: 'Поддоны с субстратом',
  ebb_flow: 'Прилив-отлив',
  nft: 'NFT',
  dwc: 'DWC',
  aeroponics: 'Аэропоника',
}

const IRRIGATION_MODE_LABELS: Record<string, string> = {
  SUBSTRATE: 'Пролив в субстрат',
  RECIRC: 'Рециркуляция',
}

const PROGRESS_MODEL_LABELS: Record<string, string> = {
  TIME: 'По времени',
  TIME_WITH_TEMP_CORRECTION: 'Время с температурной коррекцией',
  GDD: 'По сумме эффективных температур (GDD)',
  DLI: 'По накопленному DLI',
}

const NUTRIENT_MODE_LABELS: Record<string, string> = {
  ratio_ec_pid: 'Пропорции + EC PID',
  delta_ec_by_k: 'Дельта EC по коэффициенту',
  dose_ml_l_only: 'Только дозы мл/л',
}

export function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

function buildRange(target: unknown, min: unknown, max: unknown): VisualRange {
  return {
    target: toNumber(target),
    min: toNumber(min),
    max: toNumber(max),
  }
}

export function rangeHasValue(range: VisualRange): boolean {
  return range.target !== null || range.min !== null || range.max !== null
}

function readDayNightPair(source: Record<string, unknown> | null, key: string): VisualDayNightPair | null {
  const pair = asRecord(source?.[key])
  if (!pair) {
    return null
  }

  const day = toNumber(pair.day)
  const night = toNumber(pair.night)
  if (day === null && night === null) {
    return null
  }

  return { day, night }
}

function buildDayNight(phase: RecipeVisualPhaseInput): VisualDayNight {
  const extensions = asRecord(phase.extensions)
  const source = asRecord(phase.day_night) ?? asRecord(extensions?.day_night)
  const lighting = asRecord(source?.lighting)

  const ph = readDayNightPair(source, 'ph')
  const ec = readDayNightPair(source, 'ec')
  const temperature = readDayNightPair(source, 'temperature')
  const humidity = readDayNightPair(source, 'humidity')
  const lightingDayHours = toNumber(lighting?.day_hours)
  const lightingStartTime = typeof lighting?.day_start_time === 'string' ? lighting.day_start_time : null

  return {
    enabled: phase.day_night_enabled === true,
    ph,
    ec,
    temperature,
    humidity,
    lightingDayHours,
    lightingStartTime,
    hasData: Boolean(ph || ec || temperature || humidity),
  }
}

function buildNutrition(phase: RecipeVisualPhaseInput): VisualNutrition {
  const components: VisualNutritionComponent[] = [
    {
      key: 'npk',
      label: NUTRITION_LABELS.npk,
      ratioPct: toNumber(phase.nutrient_npk_ratio_pct),
      doseMlL: toNumber(phase.nutrient_npk_dose_ml_l),
      product: phase.npk_product ?? null,
      productId: toNumber(phase.nutrient_npk_product_id),
    },
    {
      key: 'calcium',
      label: NUTRITION_LABELS.calcium,
      ratioPct: toNumber(phase.nutrient_calcium_ratio_pct),
      doseMlL: toNumber(phase.nutrient_calcium_dose_ml_l),
      product: phase.calcium_product ?? null,
      productId: toNumber(phase.nutrient_calcium_product_id),
    },
    {
      key: 'magnesium',
      label: NUTRITION_LABELS.magnesium,
      ratioPct: toNumber(phase.nutrient_magnesium_ratio_pct),
      doseMlL: toNumber(phase.nutrient_magnesium_dose_ml_l),
      product: phase.magnesium_product ?? null,
      productId: toNumber(phase.nutrient_magnesium_product_id),
    },
    {
      key: 'micro',
      label: NUTRITION_LABELS.micro,
      ratioPct: toNumber(phase.nutrient_micro_ratio_pct),
      doseMlL: toNumber(phase.nutrient_micro_dose_ml_l),
      product: phase.micro_product ?? null,
      productId: toNumber(phase.nutrient_micro_product_id),
    },
  ]

  const ratioSum = components.reduce((sum, item) => sum + (item.ratioPct ?? 0), 0)
  const hasData = components.some(
    (item) => item.ratioPct !== null || item.doseMlL !== null || item.productId !== null,
  )

  return {
    programCode: phase.nutrient_program_code ?? null,
    mode: phase.nutrient_mode ?? null,
    ecDosingMode: phase.nutrient_ec_dosing_mode ?? null,
    solutionVolumeL: toNumber(phase.nutrient_solution_volume_l),
    doseDelaySec: toNumber(phase.nutrient_dose_delay_sec),
    ecStopTolerance: toNumber(phase.nutrient_ec_stop_tolerance),
    components,
    ratioSum,
    hasData: hasData || Boolean(phase.nutrient_program_code),
  }
}

function resolveDurationHours(phase: RecipeVisualPhaseInput): number | null {
  const hours = toNumber(phase.duration_hours)
  if (hours !== null) {
    return hours
  }

  const days = toNumber(phase.duration_days)
  return days === null ? null : days * 24
}

function resolveSystemType(phase: RecipeVisualPhaseInput): string | null {
  if (typeof phase.irrigation_system_type === 'string' && phase.irrigation_system_type) {
    return phase.irrigation_system_type
  }

  const extensions = asRecord(phase.extensions)
  const subsystems = asRecord(extensions?.subsystems)
  const irrigation = asRecord(subsystems?.irrigation)
  const targets = asRecord(irrigation?.targets)
  const execution = asRecord(irrigation?.execution)
  const fromTargets = targets?.system_type
  const fromExecution = execution?.system_type

  if (typeof fromTargets === 'string' && fromTargets) {
    return fromTargets
  }

  return typeof fromExecution === 'string' && fromExecution ? fromExecution : null
}

/**
 * Преобразует фазы рецепта в единый вид для визуализации,
 * рассчитывая накопительные границы фаз по оси времени цикла.
 */
export function buildRecipePhaseVisuals(phases: RecipeVisualPhaseInput[] | null | undefined): RecipePhaseVisual[] {
  if (!Array.isArray(phases) || phases.length === 0) {
    return []
  }

  const sorted = [...phases].sort((a, b) => Number(a.phase_index ?? 0) - Number(b.phase_index ?? 0))
  let cursorHours = 0

  return sorted.map((phase, position) => {
    const extensions = asRecord(phase.extensions)
    const lightingExt = asRecord(extensions?.lighting)
    const agronomyExt = asRecord(extensions?.agronomy)
    const durationHours = resolveDurationHours(phase)
    const startHours = cursorHours
    const endHours = startHours + (durationHours ?? 0)
    cursorHours = endHours

    const criticalControls = typeof agronomyExt?.critical_controls === 'string' ? agronomyExt.critical_controls : null
    const riskFocus = typeof agronomyExt?.risk_focus === 'string' ? agronomyExt.risk_focus : null

    return {
      key: String(phase.id ?? `phase-${position}`),
      position,
      index: Number(phase.phase_index ?? position),
      name: String(phase.name ?? `Фаза ${position + 1}`),
      stageName: phase.stage_template?.name ?? null,
      durationHours,
      startHours,
      endHours,
      startDay: startHours / 24,
      endDay: endHours / 24,
      ph: buildRange(
        phase.ph_target ?? phase.targets?.ph?.target,
        phase.ph_min ?? phase.targets?.ph?.min,
        phase.ph_max ?? phase.targets?.ph?.max,
      ),
      ec: buildRange(
        phase.ec_target ?? phase.targets?.ec?.target,
        phase.ec_min ?? phase.targets?.ec?.min,
        phase.ec_max ?? phase.targets?.ec?.max,
      ),
      temperature: buildRange(
        phase.temp_air_target ?? phase.targets?.temp_air,
        extensions?.temp_air_min,
        extensions?.temp_air_max,
      ),
      humidity: buildRange(
        phase.humidity_target ?? phase.targets?.humidity_air,
        extensions?.humidity_min,
        extensions?.humidity_max,
      ),
      co2: buildRange(phase.co2_target, extensions?.co2_min, extensions?.co2_max),
      dli: buildRange(phase.dli_target, extensions?.dli_min, extensions?.dli_max),
      solutionTemp: buildRange(
        phase.solution_temp_target ?? phase.targets?.solution_temp?.target,
        phase.solution_temp_min ?? phase.targets?.solution_temp?.min,
        phase.solution_temp_max ?? phase.targets?.solution_temp?.max,
      ),
      lightHours: toNumber(phase.lighting_photoperiod_hours ?? phase.targets?.light_hours),
      lightStartTime: phase.lighting_start_time ?? null,
      ppfd: toNumber(lightingExt?.ppfd),
      irrigation: {
        mode: phase.irrigation_mode ?? null,
        systemType: resolveSystemType(phase),
        substrateType: phase.substrate_type ?? null,
        intervalSec: toNumber(phase.irrigation_interval_sec ?? phase.targets?.irrigation_interval_sec),
        durationSec: toNumber(phase.irrigation_duration_sec ?? phase.targets?.irrigation_duration_sec),
      },
      mist: {
        mode: phase.mist_mode ?? null,
        intervalSec: toNumber(phase.mist_interval_sec),
        durationSec: toNumber(phase.mist_duration_sec),
      },
      nutrition: buildNutrition(phase),
      dayNight: buildDayNight(phase),
      progressModel: phase.progress_model ?? null,
      advanceStrategy: phase.phase_advance_strategy ?? null,
      targetGdd: toNumber(phase.target_gdd),
      baseTempC: toNumber(phase.base_temp_c),
      agronomy: criticalControls || riskFocus ? { criticalControls, riskFocus } : null,
    }
  })
}

function summarizeRange(values: Array<number | null>): VisualRange {
  const known = values.filter((value): value is number => value !== null)
  if (known.length === 0) {
    return { target: null, min: null, max: null }
  }

  return {
    target: null,
    min: Math.min(...known),
    max: Math.max(...known),
  }
}

export function summarizeRecipePhases(phases: RecipePhaseVisual[]): RecipeVisualSummary {
  const durations = phases
    .map((phase) => phase.durationHours)
    .filter((value): value is number => value !== null)
  const totalHours = durations.length > 0 ? durations.reduce((sum, value) => sum + value, 0) : null

  const collect = (pick: (phase: RecipePhaseVisual) => Array<number | null>): VisualRange =>
    summarizeRange(phases.flatMap(pick))

  return {
    phaseCount: phases.length,
    totalHours,
    totalDays: totalHours === null ? null : totalHours / 24,
    ph: collect((phase) => [phase.ph.min, phase.ph.max, phase.ph.target]),
    ec: collect((phase) => [phase.ec.min, phase.ec.max, phase.ec.target]),
    temperature: collect((phase) => [phase.temperature.min, phase.temperature.max, phase.temperature.target]),
    humidity: collect((phase) => [phase.humidity.min, phase.humidity.max, phase.humidity.target]),
    lightHours: collect((phase) => [phase.lightHours]),
    co2: collect((phase) => [phase.co2.min, phase.co2.max, phase.co2.target]),
  }
}

export function formatNumberValue(value: number | null, digits = 1): string {
  if (value === null) {
    return '—'
  }

  const rounded = Math.round(value * 10 ** digits) / 10 ** digits
  return String(rounded)
}

export function formatRangeValue(range: VisualRange, unit = '', digits = 1): string {
  if (!rangeHasValue(range)) {
    return '—'
  }

  const min = range.min ?? range.target
  const max = range.max ?? range.target
  const suffix = unit ? ` ${unit}` : ''

  if (min !== null && max !== null && min !== max) {
    return `${formatNumberValue(min, digits)}–${formatNumberValue(max, digits)}${suffix}`
  }

  return `${formatNumberValue(range.target ?? min ?? max, digits)}${suffix}`
}

export function formatDurationHours(hours: number | null): string {
  if (hours === null || hours <= 0) {
    return '—'
  }

  if (hours < 24) {
    return `${formatNumberValue(hours, 0)} ч`
  }

  const days = Math.floor(hours / 24)
  const rest = Math.round(hours % 24)
  return rest === 0 ? `${days} дн` : `${days} дн ${rest} ч`
}

export function formatDayRange(phase: RecipePhaseVisual): string {
  if (phase.durationHours === null) {
    return 'длительность не задана'
  }

  const start = Math.round(phase.startDay * 10) / 10
  const end = Math.round(phase.endDay * 10) / 10
  return `дни ${start}–${end}`
}

export function formatInterval(seconds: number | null): string {
  if (seconds === null || seconds <= 0) {
    return '—'
  }

  if (seconds < 60) {
    return `${Math.round(seconds)} с`
  }

  const minutes = seconds / 60
  if (minutes < 60) {
    return `${Math.round(minutes)} мин`
  }

  const hours = Math.round((minutes / 60) * 10) / 10
  return `${hours} ч`
}

export function formatTimeOfDay(value: string | null): string {
  if (!value) {
    return '—'
  }

  const match = /^(\d{2}):(\d{2})/.exec(value)
  return match ? `${match[1]}:${match[2]}` : value
}

export function irrigationSystemLabel(systemType: string | null): string {
  if (!systemType) {
    return '—'
  }

  return IRRIGATION_SYSTEM_LABELS[systemType] ?? systemType
}

export function irrigationModeLabel(mode: string | null): string {
  if (!mode) {
    return '—'
  }

  return IRRIGATION_MODE_LABELS[mode.toUpperCase()] ?? mode
}

export function progressModelLabel(model: string | null): string {
  if (!model) {
    return '—'
  }

  return PROGRESS_MODEL_LABELS[model.toUpperCase()] ?? model
}

export function nutrientModeLabel(mode: string | null): string {
  if (!mode) {
    return '—'
  }

  return NUTRIENT_MODE_LABELS[mode] ?? mode
}

export function productLabel(component: VisualNutritionComponent): string {
  if (component.product?.manufacturer || component.product?.name) {
    return [component.product?.manufacturer, component.product?.name].filter(Boolean).join(' · ')
  }

  return component.productId ? `ID ${component.productId}` : '—'
}

/** Палитра сегментов таймлайна: цвета повторяются по кругу для длинных рецептов. */
export const PHASE_COLORS = [
  'var(--accent-green)',
  'var(--accent-cyan)',
  'var(--accent-amber)',
  'var(--accent-lime)',
  'var(--accent-red)',
] as const

export function phaseColor(index: number): string {
  return PHASE_COLORS[index % PHASE_COLORS.length]
}
