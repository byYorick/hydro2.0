import type { AutomationHangHint, AutomationState, ZoneDayBalance } from '@/types/Automation'

/** Числа суток показываются как в read-model: интеграл и миллилитры здесь не считаются. */

const UNAVAILABLE_DLI_STATUSES = new Set(['not_configured', 'sensor_unavailable', 'gap'])

const DLI_STATUS_LABELS: Record<string, string> = {
  not_configured: 'не задано',
  sensor_unavailable: 'датчик недоступен',
  gap: 'разрыв ряда',
  capped: 'потолок достигнут',
  within_target: 'в пределах цели',
}

const CROP_DAY_HINT_CODES = new Set([
  'irrigation_sensor_blocked',
  'solution_temp_blocked',
  'dli_sensor_unavailable',
  'dli_gap',
  'solution_refresh_due',
  'moisture_vent_suppressed',
])

export interface CropDayHintView {
  code: string
  message: string
  recommendation: string | null
}

export interface CropDayView {
  dateLabel: string
  timezoneLabel: string
  irrigationCommandsLabel: string
  commandedSecLabel: string
  commandedMlLabel: string
  lightLabel: string
  photoperiodLabel: string | null
  brightnessLabel: string | null
  climateMissing: boolean
  airVpdLabel: string
  dewPointLabel: string
  moistureSuppressedLabel: string
  solutionTempLabel: string
  solutionGateLabel: string
  solutionRefreshLabel: string
  hints: CropDayHintView[]
}

export function readUnknownRecord(raw: unknown): Record<string, unknown> | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null
  }
  return raw as Record<string, unknown>
}

export function normalizeDayBalance(raw: unknown): ZoneDayBalance | null {
  const source = readUnknownRecord(raw)
  if (!source) {
    return null
  }

  const balance: ZoneDayBalance = {}
  assignString(balance, source, 'local_date')
  assignString(balance, source, 'window_start')
  assignString(balance, source, 'window_end')
  assignString(balance, source, 'timezone')
  assignBoolean(balance, source, 'timezone_fallback')
  assignNumber(balance, source, 'irrigation_commands')
  assignNumber(balance, source, 'commanded_sec')
  assignNumber(balance, source, 'commanded_ml')
  assignString(balance, source, 'commanded_ml_status')
  assignNumber(balance, source, 'dli_mol')
  assignString(balance, source, 'dli_status')
  assignNumber(balance, source, 'air_vpd_kpa')
  assignNumber(balance, source, 'dew_point_c')
  assignBoolean(balance, source, 'moisture_vent_suppressed')
  assignNumber(balance, source, 'solution_temp_c')
  assignNumber(balance, source, 'photoperiod_hours')
  assignNumber(balance, source, 'brightness')
  assignBoolean(balance, source, 'solution_health_required')

  const health = readUnknownRecord(source.solution_health)
  if (health && typeof health.required === 'boolean') {
    balance.solution_health = { required: health.required }
  } else if (Object.prototype.hasOwnProperty.call(source, 'solution_health') && source.solution_health === null) {
    balance.solution_health = null
  }

  return balance
}

export function readOptionalSolutionTemp(raw: unknown): number | null {
  const source = readUnknownRecord(raw)
  if (!source || !Object.prototype.hasOwnProperty.call(source, 'solution_temp_c')) {
    return null
  }
  return finiteOrNull(source.solution_temp_c)
}

export function resolveCropDayView(
  state: AutomationState | null,
  recipePhase?: unknown,
): CropDayView {
  const balance = state?.day_balance ?? null
  const climate = readClimate(state)
  const hints = readCropDayHints(state)
  const gateRequired = readGateRequired(state, recipePhase)
  const blockedByHint = hints.some((hint) => hint.code === 'solution_temp_blocked')
  const refreshHint = hints.some((hint) => hint.code === 'solution_refresh_due')

  return {
    dateLabel: textOr(balance?.local_date, 'нет даты'),
    timezoneLabel: timezoneLabel(balance),
    irrigationCommandsLabel: commandsLabel(balance),
    commandedSecLabel: secondsLabel(balance),
    commandedMlLabel: millilitersLabel(balance),
    lightLabel: lightLabel(balance),
    photoperiodLabel: optionalHours(balance, ['photoperiod_hours']),
    brightnessLabel: optionalPlain(balance, ['brightness']),
    climateMissing: !climate.present,
    airVpdLabel: climate.airVpd == null ? 'нет' : `${formatReadNumber(climate.airVpd)} кПа`,
    dewPointLabel: climate.dewPoint == null ? 'нет' : `${formatReadNumber(climate.dewPoint)} °C`,
    moistureSuppressedLabel: climate.suppressed == null
      ? 'нет в снимке'
      : (climate.suppressed ? 'да' : 'нет'),
    solutionTempLabel: solutionTempLabel(state),
    solutionGateLabel: gateLabel(gateRequired, blockedByHint),
    solutionRefreshLabel: refreshLabel(state, refreshHint),
    hints,
  }
}

function timezoneLabel(balance: ZoneDayBalance | null): string {
  if (!balance) {
    return 'нет данных'
  }
  if (balance.timezone_fallback === true) {
    return 'UTC, пояс не задан'
  }
  const name = typeof balance.timezone === 'string' ? balance.timezone.trim() : ''
  if (name !== '') {
    return name
  }
  return 'пояс теплицы'
}

function commandsLabel(balance: ZoneDayBalance | null): string {
  if (!balance || balance.irrigation_commands == null || !Number.isFinite(balance.irrigation_commands)) {
    return 'нет данных'
  }
  return formatReadNumber(balance.irrigation_commands)
}

function secondsLabel(balance: ZoneDayBalance | null): string {
  if (!balance || balance.commanded_sec == null || !Number.isFinite(balance.commanded_sec)) {
    return 'нет данных'
  }
  return `${formatReadNumber(balance.commanded_sec)} с`
}

function millilitersLabel(balance: ZoneDayBalance | null): string {
  if (!balance) {
    return 'нет данных'
  }
  const status = (balance.commanded_ml_status ?? '').trim().toLowerCase()
  if (status === 'calibration_missing' || balance.commanded_ml == null) {
    return 'нет калибровки канала'
  }
  const commands = balance.irrigation_commands
  if (commands == null || commands === 0) {
    return 'нет команд'
  }
  return `${formatReadNumber(balance.commanded_ml)} мл`
}

function lightLabel(balance: ZoneDayBalance | null): string {
  if (!balance) {
    return 'нет данных'
  }
  const status = (balance.dli_status ?? '').trim().toLowerCase()
  if (UNAVAILABLE_DLI_STATUSES.has(status)) {
    return DLI_STATUS_LABELS[status] ?? status
  }
  const mol = balance.dli_mol
  const statusLabel = status !== '' ? (DLI_STATUS_LABELS[status] ?? null) : null
  if (mol == null || !Number.isFinite(mol)) {
    return statusLabel ?? 'нет данных'
  }
  const value = `${formatReadNumber(mol)} моль/м²`
  return statusLabel ? `${value} · ${statusLabel}` : value
}

function optionalHours(balance: ZoneDayBalance | null, keys: Array<keyof ZoneDayBalance>): string | null {
  const value = firstBalanceNumber(balance, keys)
  if (value == null) {
    return null
  }
  return `${formatReadNumber(value)} ч`
}

function optionalPlain(balance: ZoneDayBalance | null, keys: Array<keyof ZoneDayBalance>): string | null {
  const value = firstBalanceNumber(balance, keys)
  if (value == null) {
    return null
  }
  return formatReadNumber(value)
}

function solutionTempLabel(state: AutomationState | null): string {
  const sources = payloadRecords(state)
  if (state?.current_levels && Object.prototype.hasOwnProperty.call(state.current_levels, 'solution_temp_c')) {
    sources.push(state.current_levels as unknown as Record<string, unknown>)
  }
  const value = firstFinite(sources, ['solution_temp_c', 'solution_temperature_c'])
  if (value == null) {
    return 'нет температуры'
  }
  return `${formatReadNumber(value)} °C`
}

function gateLabel(required: boolean | undefined, blockedByHint: boolean): string {
  if (required === true) {
    return 'включён'
  }
  if (required === false) {
    return 'выключен'
  }
  if (blockedByHint) {
    return 'блокировка есть'
  }
  return 'нет данных'
}

function refreshLabel(state: AutomationState | null, refreshHint: boolean): string {
  if (refreshHint) {
    return 'есть рекомендация подмены'
  }
  if (state?.observability) {
    return 'рекомендации подмены нет'
  }
  return 'нет данных'
}

function readClimate(state: AutomationState | null): {
  present: boolean
  airVpd: number | null
  dewPoint: number | null
  suppressed: boolean | null
} {
  const sources = payloadRecords(state)
  const airVpd = firstFinite(sources, ['air_vpd_kpa'])
  const dewPoint = firstFinite(sources, ['dew_point_c'])
  const suppressed = firstBoolean(sources, ['moisture_vent_suppressed'])
  const present = airVpd != null || dewPoint != null || suppressed != null
  return {
    present,
    airVpd: airVpd ?? null,
    dewPoint: dewPoint ?? null,
    suppressed: suppressed ?? null,
  }
}

function readGateRequired(state: AutomationState | null, recipePhase: unknown): boolean | undefined {
  const fromBalance = readRequiredFlag(state?.day_balance as unknown as Record<string, unknown> | null | undefined)
  if (fromBalance !== undefined) {
    return fromBalance
  }
  for (const source of payloadRecords(state)) {
    const required = readRequiredFlag(source)
    if (required !== undefined) {
      return required
    }
  }
  const phase = readUnknownRecord(recipePhase)
  const extensions = readUnknownRecord(phase?.extensions)
  return readRequiredFlag(extensions)
}

function readRequiredFlag(source: Record<string, unknown> | null | undefined): boolean | undefined {
  if (!source) {
    return undefined
  }
  if (typeof source.solution_health_required === 'boolean') {
    return source.solution_health_required
  }
  const health = readUnknownRecord(source.solution_health)
  if (health && typeof health.required === 'boolean') {
    return health.required
  }
  return undefined
}

function readCropDayHints(state: AutomationState | null): CropDayHintView[] {
  const hints = state?.observability?.hang_hints ?? []
  return hints
    .filter((hint): hint is AutomationHangHint => Boolean(hint) && CROP_DAY_HINT_CODES.has(hint.code))
    .map((hint) => ({
      code: hint.code,
      message: typeof hint.message === 'string' ? hint.message.trim() : '',
      recommendation: typeof hint.recommendation === 'string' && hint.recommendation.trim() !== ''
        ? hint.recommendation.trim()
        : null,
    }))
    .filter((hint) => hint.message !== '' || hint.recommendation !== null)
}

function payloadRecords(state: AutomationState | null): Record<string, unknown>[] {
  if (!state) {
    return []
  }
  const sources: Record<string, unknown>[] = []
  if (state.day_balance) {
    sources.push(state.day_balance as unknown as Record<string, unknown>)
  }
  if (state.decision_factors) {
    sources.push(state.decision_factors)
  }
  if (state.decision?.factors) {
    sources.push(state.decision.factors)
  }
  return sources
}

function firstFinite(sources: Record<string, unknown>[], keys: string[]): number | undefined {
  for (const source of sources) {
    for (const key of keys) {
      if (!Object.prototype.hasOwnProperty.call(source, key)) {
        continue
      }
      const value = finiteOrNull(source[key])
      if (value != null) {
        return value
      }
    }
  }
  return undefined
}

function firstBoolean(sources: Record<string, unknown>[], keys: string[]): boolean | undefined {
  for (const source of sources) {
    for (const key of keys) {
      if (typeof source[key] === 'boolean') {
        return source[key]
      }
    }
  }
  return undefined
}

function firstBalanceNumber(balance: ZoneDayBalance | null, keys: Array<keyof ZoneDayBalance>): number | null {
  if (!balance) {
    return null
  }
  const source = balance as unknown as Record<string, unknown>
  const value = firstFinite([source], keys.map((key) => String(key)))
  return value ?? null
}

function textOr(value: string | null | undefined, fallback: string): string {
  if (typeof value !== 'string') {
    return fallback
  }
  const trimmed = value.trim()
  return trimmed === '' ? fallback : trimmed
}

function formatReadNumber(value: number): string {
  return String(value)
}

function assignString<K extends 'local_date' | 'window_start' | 'window_end' | 'timezone' | 'commanded_ml_status' | 'dli_status'>(
  target: ZoneDayBalance,
  source: Record<string, unknown>,
  key: K,
): void {
  if (!Object.prototype.hasOwnProperty.call(source, key)) {
    return
  }
  const value = source[key]
  target[key] = typeof value === 'string' ? value : null
}

function assignNumber<K extends 'irrigation_commands' | 'commanded_sec' | 'commanded_ml' | 'dli_mol' | 'air_vpd_kpa' | 'dew_point_c' | 'solution_temp_c' | 'photoperiod_hours' | 'brightness'>(
  target: ZoneDayBalance,
  source: Record<string, unknown>,
  key: K,
): void {
  if (!Object.prototype.hasOwnProperty.call(source, key)) {
    return
  }
  target[key] = finiteOrNull(source[key])
}

function assignBoolean<K extends 'timezone_fallback' | 'moisture_vent_suppressed' | 'solution_health_required'>(
  target: ZoneDayBalance,
  source: Record<string, unknown>,
  key: K,
): void {
  if (!Object.prototype.hasOwnProperty.call(source, key)) {
    return
  }
  target[key] = typeof source[key] === 'boolean' ? source[key] : undefined
}

function finiteOrNull(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}
