/**
 * Pure data builder: converts event payload into { label, value }[] rows.
 * No h() / render functions — template renders these with v-for.
 */
import {
  boolLabel,
  firstNumber,
  firstString,
  formatPayloadNumber,
  humanizeEventError,
  readNumber,
  readString,
  toPayloadRecord,
} from '@/utils/eventPayload'
import type { ZoneEvent } from '@/types/ZoneEvent'

export interface DetailRow {
  label: string
  value: string
  variant?: 'default' | 'error'
}

type Payload = Record<string, unknown>

function row(label: string, value: string, variant: DetailRow['variant'] = 'default'): DetailRow {
  return { label, value, variant }
}

function appendCorrectionTrace(rows: DetailRow[], payload: Payload): void {
  const windowId = readString(payload, 'correction_window_id')
  const taskId = readNumber(payload, 'task_id')
  const workflowPhase = readString(payload, 'workflow_phase')
  const stage = readString(payload, 'stage')
  const observeSeq = readNumber(payload, 'observe_seq')
  const decisionReason = readString(payload, 'decision_reason')

  if (windowId) rows.push(row('Окно коррекции', windowId))
  if (taskId !== null) rows.push(row('Задача ID', String(taskId)))
  if (workflowPhase) rows.push(row('Фаза', workflowPhase))
  if (stage) rows.push(row('Стадия', stage))
  if (observeSeq !== null) rows.push(row('Наблюдение', `#${observeSeq}`))
  if (decisionReason) rows.push(row('Причина выбора', decisionReason))
}

function appendIrrigationDecisionConfigRows(rows: DetailRow[], payload: Payload): void {
  const config = toPayloadRecord(payload['config']) ?? toPayloadRecord(payload['decision_config'])
  if (!config) return

  const lookbackSec = readNumber(config, 'lookback_sec')
  const minSamples = readNumber(config, 'min_samples')
  const staleAfterSec = readNumber(config, 'stale_after_sec')
  const hysteresisPct = readNumber(config, 'hysteresis_pct')
  const spreadThresholdPct = readNumber(config, 'spread_alert_threshold_pct')

  if (lookbackSec !== null) rows.push(row('Lookback', `${lookbackSec} с`))
  if (minSamples !== null) rows.push(row('Min samples', String(minSamples)))
  if (staleAfterSec !== null) rows.push(row('Stale after', `${staleAfterSec} с`))
  if (hysteresisPct !== null) rows.push(row('Hysteresis', `${hysteresisPct}%`))
  if (spreadThresholdPct !== null) rows.push(row('Spread alert', `${spreadThresholdPct}%`))
}

function buildIrrSnapshot(payload: Payload): Array<{ label: string, value: string }> {
  const snapshot = toPayloadRecord(payload['snapshot'])
  if (!snapshot) return []
  const labelMap: Record<string, string> = {
    pump_main: 'Насос (основной)',
    valve_clean_fill: 'Клапан заполнения чистой',
    valve_clean_supply: 'Клапан подачи чистой воды',
    valve_solution_fill: 'Клапан заполнения раствора',
    valve_solution_supply: 'Клапан подачи раствора',
    valve_irrigation: 'Клапан полива',
    valve_drain: 'Клапан слива',
    valve_recirc: 'Клапан рециркуляции',
    clean_level_max: 'Уровень чистой (макс)',
    clean_level_min: 'Уровень чистой (мин)',
    solution_level_max: 'Уровень раствора (макс)',
    solution_level_min: 'Уровень раствора (мин)',
  }
  return Object.entries(snapshot).map(([key, val]) => ({
    label: labelMap[key] ?? key.replace(/_/g, ' '),
    value: typeof val === 'boolean' ? boolLabel(val) : String(val ?? '—'),
  }))
}

export function buildEventDetails(event: ZoneEvent): DetailRow[] {
  const payload = toPayloadRecord(event.payload)
  if (!payload) return []

  const rows: DetailRow[] = []

  if (event.kind === 'IRR_STATE_SNAPSHOT') {
    const nodeUid = readString(payload, 'node_uid')
    const cmdId = readString(payload, 'cmd_id')
    if (nodeUid) rows.push(row('Нода', nodeUid))
    if (cmdId) rows.push(row('Команда', cmdId))
    buildIrrSnapshot(payload).forEach(r => rows.push(row(r.label, r.value)))
  }
  else if (event.kind === 'COMMAND_TIMEOUT') {
    const cmdId = readString(payload, 'cmd_id')
    const timeout = readNumber(payload, 'timeout_minutes')
    const commandId = readNumber(payload, 'command_id')
    if (cmdId) rows.push(row('Команда', cmdId))
    if (timeout !== null) rows.push(row('Таймаут', `${timeout} мин`))
    if (commandId !== null) rows.push(row('ID команды', String(commandId)))
  }
  else if (event.kind === 'PUMP_CALIBRATION_FINISHED' || event.kind === 'PUMP_CALIBRATION_SAVED') {
    const component = firstString(payload, ['component', 'role'])
    const actualMl = readNumber(payload, 'actual_ml')
    const mlPerSec = readNumber(payload, 'ml_per_sec')
    const nodeUid = readString(payload, 'node_uid')
    const channel = readString(payload, 'channel')
    if (component) rows.push(row('Компонент', component))
    if (actualMl !== null) rows.push(row('Объём', `${actualMl.toFixed(2)} мл`))
    if (mlPerSec !== null) rows.push(row('Скорость', `${mlPerSec.toFixed(2)} мл/с`))
    if (nodeUid) rows.push(row('Нода', nodeUid))
    if (channel) rows.push(row('Канал', channel))
  }
  else if (event.kind === 'PUMP_CALIBRATION_RUN_SKIPPED') {
    const component = readString(payload, 'component')
    const nodeUid = readString(payload, 'node_uid')
    const channel = readString(payload, 'channel')
    const durationSec = readNumber(payload, 'duration_sec')
    const reason = firstString(payload, ['reason', 'reason_code'])
    if (component) rows.push(row('Компонент', component))
    if (nodeUid) rows.push(row('Нода', nodeUid))
    if (channel) rows.push(row('Канал', channel))
    if (durationSec !== null) rows.push(row('Длительность теста', `${durationSec} с`))
    if (reason) rows.push(row('Причина', reason))
  }
  else if (event.kind === 'EC_DOSING') {
    const currentEc = readNumber(payload, 'current_ec')
    const targetEc = readNumber(payload, 'target_ec')
    const targetEcMin = readNumber(payload, 'target_ec_min')
    const targetEcMax = readNumber(payload, 'target_ec_max')
    const durationMs = readNumber(payload, 'duration_ms')
    const amountMl = readNumber(payload, 'amount_ml')
    const ecComponent = readString(payload, 'ec_component')
    const nodeUid = readString(payload, 'node_uid')
    const channel = readString(payload, 'channel')
    const attempt = readNumber(payload, 'attempt')
    appendCorrectionTrace(rows, payload)
    if (ecComponent) rows.push(row('Компонент', ecComponent))
    if (currentEc !== null) rows.push(row('Текущий EC', `${currentEc.toFixed(2)} мС/см`))
    if (targetEcMin !== null && targetEcMax !== null) {
      rows.push(row('Цель EC', `${targetEcMin.toFixed(2)}–${targetEcMax.toFixed(2)} мС/см`))
    } else if (targetEc !== null) {
      rows.push(row('Цель EC', `${targetEc.toFixed(2)} мС/см`))
    }
    if (amountMl !== null) rows.push(row('Доза', `${amountMl.toFixed(1)} мл`))
    if (durationMs !== null) rows.push(row('Импульс насоса', `${durationMs} мс`))
    if (nodeUid) rows.push(row('Нода', nodeUid))
    if (channel) rows.push(row('Канал', channel))
    if (attempt !== null && attempt > 1) rows.push(row('Попытка', String(attempt)))
  }
  else if (event.kind === 'PH_CORRECTED') {
    const currentPh = readNumber(payload, 'current_ph')
    const targetPh = readNumber(payload, 'target_ph')
    const targetPhMin = readNumber(payload, 'target_ph_min')
    const targetPhMax = readNumber(payload, 'target_ph_max')
    const durationMs = readNumber(payload, 'duration_ms')
    const amountMl = readNumber(payload, 'amount_ml')
    const direction = readString(payload, 'direction')
    const nodeUid = readString(payload, 'node_uid')
    const channel = readString(payload, 'channel')
    const attempt = readNumber(payload, 'attempt')
    const dirLabel = direction === 'up' ? 'вверх ↑' : direction === 'down' ? 'вниз ↓' : direction
    appendCorrectionTrace(rows, payload)
    if (dirLabel) rows.push(row('Направление', dirLabel))
    if (currentPh !== null) rows.push(row('Текущий pH', currentPh.toFixed(2)))
    if (targetPhMin !== null && targetPhMax !== null) {
      rows.push(row('Цель pH', `${targetPhMin.toFixed(2)}–${targetPhMax.toFixed(2)}`))
    } else if (targetPh !== null) {
      rows.push(row('Цель pH', targetPh.toFixed(2)))
    }
    if (amountMl !== null) rows.push(row('Доза', `${amountMl.toFixed(1)} мл`))
    if (durationMs !== null) rows.push(row('Импульс насоса', `${durationMs} мс`))
    if (nodeUid) rows.push(row('Нода', nodeUid))
    if (channel) rows.push(row('Канал', channel))
    if (attempt !== null && attempt > 1) rows.push(row('Попытка', String(attempt)))
  }
  else if (event.kind === 'CORRECTION_DECISION_MADE') {
    const selectedAction = readString(payload, 'selected_action')
    const currentPh = readNumber(payload, 'current_ph')
    const currentEc = readNumber(payload, 'current_ec')
    const needsEc = payload.needs_ec === true
    const needsPhUp = payload.needs_ph_up === true
    const needsPhDown = payload.needs_ph_down === true
    appendCorrectionTrace(rows, payload)
    if (selectedAction) rows.push(row('Выбранный контур', selectedAction))
    if (currentPh !== null) rows.push(row('Текущий pH', currentPh.toFixed(3)))
    if (currentEc !== null) rows.push(row('Текущий EC', `${currentEc.toFixed(3)} мС/см`))
    rows.push(row('Потребность EC', needsEc ? 'да' : 'нет'))
    rows.push(row('Потребность pH+', needsPhUp ? 'да' : 'нет'))
    rows.push(row('Потребность pH-', needsPhDown ? 'да' : 'нет'))
  }
  else if (event.kind === 'CORRECTION_OBSERVATION_EVALUATED') {
    const pidType = readString(payload, 'pid_type')
    const baselineValue = readNumber(payload, 'baseline_value')
    const observedValue = readNumber(payload, 'observed_value')
    const actualEffect = readNumber(payload, 'actual_effect')
    const expectedEffect = readNumber(payload, 'expected_effect')
    const thresholdEffect = readNumber(payload, 'threshold_effect')
    const noEffect = payload.is_no_effect === true
    appendCorrectionTrace(rows, payload)
    if (pidType) rows.push(row('Контур', pidType.toUpperCase()))
    if (baselineValue !== null) rows.push(row('База', baselineValue.toFixed(4)))
    if (observedValue !== null) rows.push(row('Наблюдение', observedValue.toFixed(4)))
    if (actualEffect !== null) rows.push(row('Факт. эффект', actualEffect.toFixed(4)))
    if (expectedEffect !== null) rows.push(row('Ожидаемый эффект', expectedEffect.toFixed(4)))
    if (thresholdEffect !== null) rows.push(row('Порог эффекта', thresholdEffect.toFixed(4)))
    rows.push(row('Реакция', noEffect ? 'нет эффекта' : 'эффект подтверждён'))
  }
  else if (event.kind === 'CORRECTION_COMPLETE') {
    const currentPh = readNumber(payload, 'current_ph')
    const currentEc = readNumber(payload, 'current_ec')
    const attempt = readNumber(payload, 'attempt')
    appendCorrectionTrace(rows, payload)
    if (currentPh !== null) rows.push(row('pH', currentPh.toFixed(2)))
    if (currentEc !== null) rows.push(row('EC', `${currentEc.toFixed(2)} мС/см`))
    if (attempt !== null) rows.push(row('Попытка', String(attempt)))
  }
  else if (event.kind === 'CORRECTION_EXHAUSTED') {
    const attempt = readNumber(payload, 'attempt')
    const maxAttempts = readNumber(payload, 'max_attempts')
    const ecAttempt = readNumber(payload, 'ec_attempt')
    const phAttempt = readNumber(payload, 'ph_attempt')
    const stage = readString(payload, 'stage')
    appendCorrectionTrace(rows, payload)
    if (attempt !== null && maxAttempts !== null) rows.push(row('Попытки', `${attempt}/${maxAttempts}`))
    if (ecAttempt !== null) rows.push(row('EC попыток', String(ecAttempt)))
    if (phAttempt !== null) rows.push(row('pH попыток', String(phAttempt)))
    if (stage) rows.push(row('Стадия', stage))
  }
  else if (event.kind === 'CORRECTION_SKIPPED_COOLDOWN') {
    const currentPh = readNumber(payload, 'current_ph')
    const currentEc = readNumber(payload, 'current_ec')
    const retrySec = readNumber(payload, 'retry_after_sec')
    if (currentPh !== null) rows.push(row('pH', currentPh.toFixed(2)))
    if (currentEc !== null) rows.push(row('EC', `${currentEc.toFixed(2)} мС/см`))
    if (retrySec !== null) rows.push(row('Повтор через', `${retrySec} с`))
  }
  else if (event.kind === 'CORRECTION_SKIPPED_DOSE_DISCARDED') {
    const reason = readString(payload, 'reason')
    const durationMs = readNumber(payload, 'computed_duration_ms')
    const minDoseMs = readNumber(payload, 'min_dose_ms')
    const doseMl = readNumber(payload, 'dose_ml')
    const mlPerSec = readNumber(payload, 'ml_per_sec')
    if (reason) rows.push(row('Причина', reason))
    if (durationMs !== null && minDoseMs !== null) rows.push(row('Импульс', `${durationMs} мс < ${minDoseMs} мс`))
    if (doseMl !== null) rows.push(row('Доза', `${doseMl.toFixed(4)} мл`))
    if (mlPerSec !== null) rows.push(row('Насос', `${mlPerSec.toFixed(4)} мл/с`))
  }
  else if (event.kind === 'CORRECTION_SKIPPED_WATER_LEVEL') {
    const levelPct = readNumber(payload, 'water_level_pct')
    const retrySec = readNumber(payload, 'retry_after_sec')
    if (levelPct !== null) rows.push(row('Уровень воды', `${levelPct.toFixed(1)}%`))
    if (retrySec !== null) rows.push(row('Повтор через', `${retrySec} с`))
  }
  else if (event.kind === 'CORRECTION_SKIPPED_FRESHNESS') {
    const sensorScope = readString(payload, 'sensor_scope')
    const sensorType = readString(payload, 'sensor_type')
    const retrySec = readNumber(payload, 'retry_after_sec')
    if (sensorScope) rows.push(row('Окно', sensorScope))
    if (sensorType) rows.push(row('Сенсор', sensorType))
    if (retrySec !== null) rows.push(row('Повтор через', `${retrySec} с`))
  }
  else if (event.kind === 'CORRECTION_SKIPPED_WINDOW_NOT_READY') {
    const sensorScope = readString(payload, 'sensor_scope')
    const sensorType = readString(payload, 'sensor_type')
    const reason = readString(payload, 'reason')
    const retrySec = readNumber(payload, 'retry_after_sec')
    const sampleCount = readNumber(payload, 'sample_count')
    const slope = readNumber(payload, 'slope')
    if (sensorScope) rows.push(row('Окно', sensorScope))
    if (sensorType) rows.push(row('Сенсор', sensorType))
    if (reason) rows.push(row('Причина', reason))
    if (sampleCount !== null) rows.push(row('Сэмплов', String(sampleCount)))
    if (slope !== null) rows.push(row('Slope', slope.toFixed(4)))
    if (retrySec !== null) rows.push(row('Повтор через', `${retrySec} с`))
  }
  else if (event.kind === 'CORRECTION_NO_EFFECT') {
    const pidType = readString(payload, 'pid_type')
    const actualEffect = readNumber(payload, 'actual_effect')
    const thresholdEffect = readNumber(payload, 'threshold_effect')
    const limit = readNumber(payload, 'no_effect_limit')
    if (pidType) rows.push(row('Контур', pidType.toUpperCase()))
    if (actualEffect !== null && thresholdEffect !== null) {
      rows.push(row('Эффект', `${actualEffect.toFixed(4)} < ${thresholdEffect.toFixed(4)}`))
    }
    if (limit !== null) rows.push(row('Лимит', String(limit)))
  }
  else if (event.kind === 'AE_TASK_STARTED' || event.kind === 'AE_TASK_COMPLETED') {
    const taskId = readNumber(payload, 'task_id')
    const topology = readString(payload, 'topology')
    const stage = readString(payload, 'stage')
    const trigger = readString(payload, 'intent_trigger')
    const bundleRevision = readString(payload, 'bundle_revision') ?? readString(payload, 'irrigation_bundle_revision')
    const decisionStrategy = readString(payload, 'irrigation_decision_strategy')
    if (taskId !== null) rows.push(row('Задача ID', String(taskId)))
    if (topology) rows.push(row('Топология', topology))
    if (stage) rows.push(row('Стадия', stage))
    if (trigger) rows.push(row('Триггер', trigger))
    if (decisionStrategy) rows.push(row('Strategy', decisionStrategy))
    if (bundleRevision) rows.push(row('Bundle', bundleRevision.slice(0, 12)))
    appendIrrigationDecisionConfigRows(rows, payload)
  }
  else if (event.kind === 'IRRIGATION_DECISION_SNAPSHOT_LOCKED') {
    const taskId = readNumber(payload, 'task_id')
    const strategy = readString(payload, 'strategy')
    const bundleRevision = readString(payload, 'bundle_revision')
    const growCycleId = readNumber(payload, 'grow_cycle_id')
    const phaseName = readString(payload, 'phase_name')
    if (taskId !== null) rows.push(row('Задача ID', String(taskId)))
    if (strategy) rows.push(row('Strategy', strategy))
    if (bundleRevision) rows.push(row('Bundle', bundleRevision.slice(0, 12)))
    if (growCycleId !== null) rows.push(row('Cycle ID', String(growCycleId)))
    if (phaseName) rows.push(row('Фаза', phaseName))
    appendIrrigationDecisionConfigRows(rows, payload)
  }
  else if (event.kind === 'AE_TASK_FAILED') {
    const taskId = readNumber(payload, 'task_id')
    const errorCode = readString(payload, 'error_code')
    const errorMessage = readString(payload, 'error_message')
    const stage = readString(payload, 'stage')
    if (taskId !== null) rows.push(row('Задача ID', String(taskId)))
    const humanError = humanizeEventError(errorCode, errorMessage)
    if (humanError) rows.push(row('Ошибка', humanError, 'error'))
    if (errorCode && humanError !== errorCode) rows.push(row('Код ошибки', errorCode, 'error'))
    if (stage) rows.push(row('Стадия', stage))
  }
  else {
    // Generic / fallback
    const dose = firstNumber(payload, ['output', 'ml'])
    const error = firstNumber(payload, ['error', 'diff'])
    const current = firstNumber(payload, ['current', 'current_ph', 'current_ec'])
    const target = firstNumber(payload, ['target', 'target_ph', 'target_ec'])
    const zoneState = firstString(payload, ['zone_state', 'pid_zone'])
    const integral = readNumber(payload, 'integral_term')
    const component = firstString(payload, ['component', 'correction_type'])
    const reasonCode = firstString(payload, ['reason_code', 'safety_skip_reason'])
    const reason = firstString(payload, ['reason'])
    const humanReason = humanizeEventError(reasonCode, reason)

    if (dose !== null) rows.push(row('Доза', `${formatPayloadNumber(dose, 3)} мл`))
    if (error !== null) rows.push(row('Ошибка', formatPayloadNumber(error, 4) ?? '—'))
    if (current !== null || target !== null) {
      rows.push(row('Текущее → Цель', `${formatPayloadNumber(current, 3) ?? '—'} → ${formatPayloadNumber(target, 3) ?? '—'}`))
    }
    if (zoneState) rows.push(row('ПИД-зона', zoneState))
    if (integral !== null) rows.push(row('Интеграл', formatPayloadNumber(integral, 4) ?? '—'))
    if (component) rows.push(row('Компонент', component))
    if (humanReason) rows.push(row('Причина', humanReason))
    if (reasonCode && humanReason !== reasonCode) rows.push(row('Код причины', reasonCode))
  }

  return rows
}
