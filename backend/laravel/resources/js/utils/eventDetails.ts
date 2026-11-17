import { row, appendCommandTimeoutDiagnostics, appendPidConfigRows, appendCorrectionTrace, appendCorrectionReadinessRows, appendDoseClampRows, appendIrrigationDecisionConfigRows, buildIrrSnapshot } from './eventDetailRows'
import type { DetailRow, Payload } from './eventDetailRows'
export type { DetailRow } from './eventDetailRows'
/**
 * Pure data builder: converts event payload into { label, value }[] rows.
 * No h() / render functions — template renders these with v-for.
 */
import {
  firstNumber,
  firstString,
  formatPayloadNumber,
  humanizeEventError,
  readNumber,
  readString,
  toPayloadRecord,
} from '@/utils/eventPayload'
import type { ZoneEvent } from '@/types/ZoneEvent'
import { irrigationDecisionFacts, irrigationOutcomeLabel, irrigationReasonPresentation, irrigationStrategyLabel } from './irrigationDecisionView'

export function buildEventDetails(event: ZoneEvent): DetailRow[] {
  const payload = toPayloadRecord(event.payload)
  if (!payload) return []

  const rows: DetailRow[] = []

  if (event.kind === 'IRR_STATE_SNAPSHOT') {
    const nodeUid = readString(payload, 'node_uid')
    const cmdId = readString(payload, 'cmd_id')
    const taskId = readNumber(payload, 'task_id')
    const workflowPhase = readString(payload, 'workflow_phase')
    const stage = readString(payload, 'stage')
    const schemaVersion = readNumber(payload, 'event_schema_version')
    if (nodeUid) rows.push(row('Нода', nodeUid))
    if (cmdId) rows.push(row('Команда', cmdId))
    if (taskId !== null) rows.push(row('Задача ID', String(taskId)))
    if (workflowPhase) rows.push(row('Фаза', workflowPhase))
    if (stage) rows.push(row('Стадия', stage))
    if (schemaVersion !== null) rows.push(row('Schema version', String(schemaVersion)))
    buildIrrSnapshot(payload).forEach(r => rows.push(row(r.label, r.value)))
  }
  else if (event.kind === 'COMMAND_TIMEOUT') {
    const cmdId = readString(payload, 'cmd_id')
    if (cmdId) rows.push(row('Команда', cmdId))
    appendCommandTimeoutDiagnostics(rows, payload)
  }
  else if (event.kind === 'command_status' || event.kind === 'COMMAND_STATUS') {
    const cmdId = readString(payload, 'cmd_id')
    const status = readString(payload, 'status')
    const errorCode = readString(payload, 'error_code')
    const errorMessage = firstString(payload, ['error', 'error_message', 'message'])
    if (cmdId) rows.push(row('Команда', cmdId))
    if (status) rows.push(row('Статус', status))
    if (status === 'TIMEOUT') {
      appendCommandTimeoutDiagnostics(rows, payload)
    }
    if (errorCode) {
      const localized = humanizeEventError(errorCode, errorMessage)
      rows.push(row('Ошибка', localized, 'error'))
    } else if (errorMessage) {
      rows.push(row('Сообщение', errorMessage))
    }
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
    appendDoseClampRows(rows, payload)
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
    appendDoseClampRows(rows, payload)
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
  else if (event.kind === 'IRRIGATION_CORRECTION_STARTED') {
    appendCorrectionTrace(rows, payload)
    const selectedAction = readString(payload, 'selected_action')
    const channel = readString(payload, 'channel')
    const nodeUid = readString(payload, 'node_uid')
    if (selectedAction) rows.push(row('Выбранный контур', selectedAction))
    if (channel) rows.push(row('Канал', channel))
    if (nodeUid) rows.push(row('Нода', nodeUid))
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
    appendCorrectionReadinessRows(rows, payload)
    if (currentPh !== null) rows.push(row('pH', currentPh.toFixed(2)))
    if (currentEc !== null) rows.push(row('EC', `${currentEc.toFixed(2)} мС/см`))
    if (attempt !== null) rows.push(row('Попытка', String(attempt)))
  }
  else if (event.kind === 'CORRECTION_INTERRUPTED_STAGE_COMPLETE') {
    const nextStage = readString(payload, 'next_stage')
    const reason = readString(payload, 'reason')
    appendCorrectionTrace(rows, payload)
    appendCorrectionReadinessRows(rows, payload)
    if (nextStage) rows.push(row('Следующий этап', nextStage))
    if (reason) rows.push(row('Причина', reason))
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
    const phReason = readString(payload, 'ph_reason')
    const ecReason = readString(payload, 'ec_reason')
    const retrySec = readNumber(payload, 'retry_after_sec')
    const sampleCount = readNumber(payload, 'sample_count')
    const slope = readNumber(payload, 'slope')
    if (sensorScope) rows.push(row('Окно', sensorScope))
    if (sensorType) rows.push(row('Сенсор', sensorType))
    if (phReason === 'sensor_out_of_bounds' || ecReason === 'sensor_out_of_bounds') {
      rows.push(row('Причина', 'сенсор вне допустимых bounds', 'error'))
    } else if (reason) {
      rows.push(row('Причина', reason))
    }
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
  else if (event.kind === 'CORRECTION_SKIPPED_DEAD_ZONE') {
    const currentPh = readNumber(payload, 'current_ph')
    const currentEc = readNumber(payload, 'current_ec')
    const retrySec = readNumber(payload, 'retry_after_sec')
    if (currentPh !== null) rows.push(row('pH', currentPh.toFixed(2)))
    if (currentEc !== null) rows.push(row('EC', `${currentEc.toFixed(2)} мС/см`))
    if (retrySec !== null) rows.push(row('Повтор через', `${retrySec} с`))
  }
  else if (event.kind === 'CORRECTION_SKIPPED_EMERGENCY_STOP') {
    const estopEventId = readNumber(payload, 'estop_event_id')
    appendCorrectionTrace(rows, payload)
    if (estopEventId !== null) rows.push(row('E-STOP event', String(estopEventId), 'error'))
  }
  else if (event.kind === 'CORRECTION_ACTION_DEFERRED') {
    const selectedAction = readString(payload, 'selected_action')
    const deferredAction = readString(payload, 'deferred_action')
    const reason = readString(payload, 'reason')
    appendCorrectionTrace(rows, payload)
    if (selectedAction) rows.push(row('Выбранный контур', selectedAction))
    if (deferredAction) rows.push(row('Отложено', deferredAction))
    if (reason) rows.push(row('Причина', reason))
  }
  else if (event.kind === 'CORRECTION_SKIPPED_BY_ALERT_BLOCK') {
    // AE3 writes alert_block_retry; retry_count kept as legacy alias.
    const retryCount = readNumber(payload, 'alert_block_retry')
      ?? readNumber(payload, 'retry_count')
    const maxRetries = readNumber(payload, 'alert_block_max_retries')
    appendCorrectionTrace(rows, payload)
    if (retryCount !== null && maxRetries !== null) {
      rows.push(row('Повторы', `${retryCount}/${maxRetries}`))
    } else if (retryCount !== null) {
      rows.push(row('Повтор', String(retryCount)))
    }
  }
  else if (event.kind === 'PUMP_CALIBRATION_MIRROR_MISMATCH') {
    const mismatches = payload.mismatches
    appendCorrectionTrace(rows, payload)
    if (Array.isArray(mismatches) && mismatches.length > 0) {
      rows.push(row('Расхождения', mismatches.map((item) => {
        if (item && typeof item === 'object') {
          const field = readString(item as Payload, 'field')
          return field ?? JSON.stringify(item)
        }
        return String(item)
      }).join(', '), 'error'))
    }
  }
  else if (event.kind === 'EC_BATCH_PARTIAL_FAILURE') {
    const failed = readString(payload, 'failed_component')
    const status = readString(payload, 'status')
    const mode = readString(payload, 'mode')
    const currentEc = readNumber(payload, 'current_ec')
    const targetEc = readNumber(payload, 'target_ec')
    const errorCode = readString(payload, 'error_code')
    const successful = payload['successful_components']
    const remaining = payload['remaining_components']
    appendCorrectionTrace(rows, payload)
    if (status) rows.push(row('Статус', status, status === 'degraded' ? 'error' : 'default'))
    if (failed) rows.push(row('Сбой компонента', failed, 'error'))
    if (Array.isArray(successful) && successful.length > 0) {
      rows.push(row('Успешные', successful.map(String).join(', ')))
    }
    if (Array.isArray(remaining) && remaining.length > 0) {
      rows.push(row('Оставшиеся', remaining.map(String).join(', ')))
    }
    if (currentEc !== null) rows.push(row('Текущий EC', `${currentEc.toFixed(2)} мС/см`))
    if (targetEc !== null) rows.push(row('Цель EC', `${targetEc.toFixed(2)} мС/см`))
    if (mode) rows.push(row('Режим', mode))
    if (errorCode) rows.push(row('Код ошибки', errorCode, 'error'))
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
    if (bundleRevision) rows.push(row('Версия настроек', bundleRevision.slice(0, 12)))
    appendIrrigationDecisionConfigRows(rows, payload)
  }
  else if (event.kind === 'IRRIGATION_DECISION_SNAPSHOT_LOCKED') {
    const taskId = readNumber(payload, 'task_id')
    const strategy = readString(payload, 'strategy')
    const bundleRevision = readString(payload, 'bundle_revision')
    const growCycleId = readNumber(payload, 'grow_cycle_id')
    const phaseName = readString(payload, 'phase_name')
    if (taskId !== null) rows.push(row('Задача ID', String(taskId)))
    if (strategy) rows.push(row('Условие полива', irrigationStrategyLabel(strategy)))
    if (bundleRevision) rows.push(row('Версия настроек', bundleRevision.slice(0, 12)))
    if (growCycleId !== null) rows.push(row('Цикл', String(growCycleId)))
    if (phaseName) rows.push(row('Фаза', phaseName))
    appendIrrigationDecisionConfigRows(rows, payload)
  }
  else if (event.kind === 'IRRIGATION_DECISION_EVALUATED') {
    const taskId = readNumber(payload, 'task_id')
    const strategy = readString(payload, 'strategy')
    const outcome = readString(payload, 'outcome')
    const reasonCode = readString(payload, 'reason_code')
    const bundleRevision = readString(payload, 'bundle_revision')
    const degradedValue = payload['degraded']
    const degraded = typeof degradedValue === 'boolean'
      ? degradedValue
      : (typeof degradedValue === 'string' ? degradedValue.toLowerCase() === 'true' : null)
    const nested = toPayloadRecord(payload['details'])
    if (taskId !== null) rows.push(row('Задача ID', String(taskId)))
    if (strategy) rows.push(row('Условие полива', irrigationStrategyLabel(strategy)))
    if (outcome) rows.push(row('Решение', irrigationOutcomeLabel(outcome)))
    if (reasonCode) {
      const reason = irrigationReasonPresentation(reasonCode)
      rows.push(row('Причина', reason.explanation))
      if (reason.action) rows.push(row('Что сделать', reason.action))
      rows.push(row('Код причины', reasonCode))
    }
    if (degraded !== null) rows.push(row('Пониженная достоверность', degraded ? 'да' : 'нет'))
    if (bundleRevision) rows.push(row('Версия настроек', bundleRevision.slice(0, 12)))
    for (const fact of irrigationDecisionFacts({ details: nested })) rows.push(row(fact.label, fact.value))
    const targetMode = nested ? readString(nested, 'target_mode') : null
    if (targetMode) rows.push(row('Способ выбора цели', targetMode))
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
  else if (event.kind === 'PID_OUTPUT') {
    const pidKind = firstString(payload, ['pid_type', 'type'])
    const zoneState = readString(payload, 'zone_state')
    const pidOut = readNumber(payload, 'output')
    const err = readNumber(payload, 'error')
    const pTerm = firstNumber(payload, ['proportional_term', 'p_term'])
    const integral = readNumber(payload, 'integral_term')
    const dTerm = firstNumber(payload, ['derivative_term', 'd_term'])
    const dtSec = readNumber(payload, 'dt_seconds')
    const current = readNumber(payload, 'current')
    const target = readNumber(payload, 'target')
    const safety = readString(payload, 'safety_skip_reason')
    if (pidKind) {
      rows.push(row('Контур', pidKind.toUpperCase()))
    }
    if (zoneState) {
      rows.push(row('Зона PID', zoneState))
    }
    if (current !== null) {
      rows.push(row('Текущее', formatPayloadNumber(current, 4) ?? String(current)))
    }
    if (target !== null) {
      rows.push(row('Цель', formatPayloadNumber(target, 4) ?? String(target)))
    }
    if (err !== null) {
      rows.push(row('Ошибка (e)', formatPayloadNumber(err, 4) ?? String(err)))
    }
    if (pidOut !== null) {
      rows.push(row('Выход (u)', `${formatPayloadNumber(pidOut, 4) ?? String(pidOut)} мл`))
    }
    if (pTerm !== null) {
      rows.push(row('P-член', formatPayloadNumber(pTerm, 4) ?? String(pTerm)))
    }
    if (integral !== null) {
      rows.push(row('I-член', formatPayloadNumber(integral, 4) ?? String(integral)))
    }
    if (dTerm !== null) {
      rows.push(row('D-член', formatPayloadNumber(dTerm, 4) ?? String(dTerm)))
    }
    if (dtSec !== null) {
      rows.push(row('Δt', `${dtSec} с`))
    }
    if (safety) {
      rows.push(row('Safety', safety))
    }
  }
  else if (event.kind === 'PID_CONFIG_UPDATED') {
    const pidKind = firstString(payload, ['pid_type', 'type'])
    const updatedByRaw = payload['updated_by']
    const updatedByLabel = updatedByRaw !== undefined && updatedByRaw !== null && String(updatedByRaw).trim() !== ''
      ? String(updatedByRaw)
      : null
    if (pidKind) {
      rows.push(row('Контур', pidKind.toUpperCase()))
    }
    if (updatedByLabel) {
      rows.push(row('Кто обновил', updatedByLabel))
    }
    appendPidConfigRows(rows, 'old_config', toPayloadRecord(payload['old_config']))
    appendPidConfigRows(rows, 'new_config', toPayloadRecord(payload['new_config']))
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
