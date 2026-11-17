import { boolLabel, readNumber, readString, toPayloadRecord } from './eventPayload'

export interface DetailRow {
  label: string
  value: string
  variant?: 'default' | 'error'
}

export type Payload = Record<string, unknown>

export function row(label: string, value: string, variant: DetailRow['variant'] = 'default'): DetailRow {
  return { label, value, variant }
}

export function appendCommandTimeoutDiagnostics(rows: DetailRow[], payload: Payload): void {
  const nodeUid = readString(payload, 'node_uid')
  const channel = readString(payload, 'channel')
  const timeout = readNumber(payload, 'timeout_minutes')
  const commandId = readNumber(payload, 'command_id')
  const nodeStatus = readString(payload, 'node_status')
  const nodeLastSeenAgeSec = readNumber(payload, 'node_last_seen_age_sec')
  const staleCandidate = payload.node_stale_online_candidate === true

  if (nodeUid) rows.push(row('Нода', nodeUid))
  if (channel) rows.push(row('Канал', channel))
  if (timeout !== null) rows.push(row('Таймаут', `${timeout} мин`))
  if (commandId !== null) rows.push(row('ID команды', String(commandId)))
  if (nodeStatus) rows.push(row('Статус узла', nodeStatus))
  if (nodeLastSeenAgeSec !== null) rows.push(row('Last seen', `${nodeLastSeenAgeSec} с назад`))
  if (staleCandidate) rows.push(row('Узел', 'online, но heartbeat устарел', 'error'))
}

function formatJsonForEventDetail(value: unknown): string | null {
  if (value === undefined || value === null) {
    return null
  }
  if (typeof value === 'string' && value.trim() !== '') {
    return value
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export function appendPidConfigRows(rows: DetailRow[], label: 'old_config' | 'new_config', config: Payload | null): void {
  if (!config) return

  const prefix = label === 'old_config' ? 'Было' : 'Стало'

  const deadZone = readNumber(config, 'dead_zone')
  const closeZone = readNumber(config, 'close_zone')
  const farZone = readNumber(config, 'far_zone')
  const maxIntegral = readNumber(config, 'max_integral')

  const zoneCoeffs = toPayloadRecord(config['zone_coeffs'])
  const closeCoeffs = zoneCoeffs ? toPayloadRecord(zoneCoeffs['close']) : null
  const farCoeffs = zoneCoeffs ? toPayloadRecord(zoneCoeffs['far']) : null

  const closeKp = closeCoeffs ? readNumber(closeCoeffs, 'kp') : null
  const closeKi = closeCoeffs ? readNumber(closeCoeffs, 'ki') : null
  const closeKd = closeCoeffs ? readNumber(closeCoeffs, 'kd') : null
  const farKp = farCoeffs ? readNumber(farCoeffs, 'kp') : null
  const farKi = farCoeffs ? readNumber(farCoeffs, 'ki') : null
  const farKd = farCoeffs ? readNumber(farCoeffs, 'kd') : null

  if (
    deadZone === null && closeZone === null && farZone === null
    && closeKp === null && farKp === null
  ) {
    const raw = formatJsonForEventDetail(config)
    if (raw) rows.push(row(prefix, raw))
    return
  }

  if (deadZone !== null) rows.push(row(`${prefix} dead_zone`, String(deadZone)))
  if (closeZone !== null) rows.push(row(`${prefix} close_zone`, String(closeZone)))
  if (farZone !== null) rows.push(row(`${prefix} far_zone`, String(farZone)))
  if (maxIntegral !== null) rows.push(row(`${prefix} max_integral`, String(maxIntegral)))

  if (closeKp !== null || closeKi !== null || closeKd !== null) {
    const parts: string[] = []
    if (closeKp !== null) parts.push(`Kp=${closeKp}`)
    if (closeKi !== null) parts.push(`Ki=${closeKi}`)
    if (closeKd !== null) parts.push(`Kd=${closeKd}`)
    rows.push(row(`${prefix} close`, parts.join('  ')))
  }
  if (farKp !== null || farKi !== null || farKd !== null) {
    const parts: string[] = []
    if (farKp !== null) parts.push(`Kp=${farKp}`)
    if (farKi !== null) parts.push(`Ki=${farKi}`)
    if (farKd !== null) parts.push(`Kd=${farKd}`)
    rows.push(row(`${prefix} far`, parts.join('  ')))
  }
}

export function appendCorrectionTrace(rows: DetailRow[], payload: Payload): void {
  const windowId = readString(payload, 'correction_window_id')
  const taskId = readNumber(payload, 'task_id')
  const workflowPhase = readString(payload, 'workflow_phase')
  const stage = readString(payload, 'stage')
  const observeSeq = readNumber(payload, 'observe_seq')
  const decisionReason = readString(payload, 'decision_reason')
  const snapshotEventId = readNumber(payload, 'snapshot_event_id')
  const causedByEventId = readNumber(payload, 'caused_by_event_id')
  const schemaVersion = readNumber(payload, 'event_schema_version')

  if (windowId) rows.push(row('Окно коррекции', windowId))
  if (taskId !== null) rows.push(row('Задача ID', String(taskId)))
  if (workflowPhase) rows.push(row('Фаза', workflowPhase))
  if (stage) rows.push(row('Стадия', stage))
  if (observeSeq !== null) rows.push(row('Наблюдение', `#${observeSeq}`))
  if (decisionReason) rows.push(row('Причина выбора', decisionReason))
  if (snapshotEventId !== null) rows.push(row('Snapshot event ID', String(snapshotEventId)))
  if (causedByEventId !== null) rows.push(row('Причинное событие ID', String(causedByEventId)))
  if (schemaVersion !== null) rows.push(row('Schema version', String(schemaVersion)))
}

export function appendCorrectionReadinessRows(rows: DetailRow[], payload: Payload): void {
  if (payload.targets_in_tolerance === true || payload.targets_in_tolerance === false) {
    rows.push(row('В допуске ±%', boolLabel(payload.targets_in_tolerance === true)))
  }
  if (payload.workflow_ready === true || payload.workflow_ready === false) {
    rows.push(row('Ready band', boolLabel(payload.workflow_ready === true)))
  }
}

export function appendDoseClampRows(rows: DetailRow[], payload: Payload): void {
  const requestedMl = readNumber(payload, 'requested_ml')
  const effectiveMl = readNumber(payload, 'effective_ml') ?? readNumber(payload, 'amount_ml')
  if (requestedMl !== null && effectiveMl !== null && requestedMl > effectiveMl + 1e-6) {
    rows.push(row('Запрошено', `${requestedMl.toFixed(4)} мл`))
    rows.push(row('Фактически', `${effectiveMl.toFixed(4)} мл (clamp)`, 'error'))
  }
}

export function appendIrrigationDecisionConfigRows(rows: DetailRow[], payload: Payload): void {
  const config = toPayloadRecord(payload['config']) ?? toPayloadRecord(payload['decision_config'])
  if (!config) return

  const lookbackSec = readNumber(config, 'lookback_sec')
  const minSamples = readNumber(config, 'min_samples')
  const staleAfterSec = readNumber(config, 'stale_after_sec')
  const hysteresisPct = readNumber(config, 'hysteresis_pct')
  const spreadThresholdPct = readNumber(config, 'spread_alert_threshold_pct')

  if (lookbackSec !== null) rows.push(row('История влажности', `${lookbackSec} с`))
  if (minSamples !== null) rows.push(row('Желаемое число измерений', String(minSamples)))
  if (staleAfterSec !== null) rows.push(row('Максимальный возраст измерения', `${staleAfterSec} с`))
  if (hysteresisPct !== null) rows.push(row('Запас ниже нижней границы', `${hysteresisPct} п.п.`))
  if (spreadThresholdPct !== null) rows.push(row('Допустимый разброс датчиков', `${spreadThresholdPct} п.п.`))
}

export function buildIrrSnapshot(payload: Payload): Array<{ label: string, value: string }> {
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
