/**
 * Операторские формулировки отказов ручных команд.
 * Сырой code API сюда не попадает: подпись остаётся русской.
 */
const MANUAL_COMMAND_REJECTION_MESSAGES: Record<string, string> = {
  estop_active: 'Аварийная остановка активна. Включающие команды отклонены, пока её не снимут.',
  node_offline: 'Узел не в сети. Команда не отправлена.',
  dose_limit_exceeded: 'Доза больше разового лимита контроллера.',
  dose_below_min_dose_ms: 'Длительность дозы меньше минимального импульса насоса.',
  dose_interval_active: 'Следующая доза этого контура ещё не разрешена.',
  dose_window_limit_exceeded: 'Суммарная доза зоны за окно превышает бюджет контроллера.',
  manual_command_rate_limited: 'Слишком много ручных команд в эту зону. Повторите позже.',
  solution_level_interlock: 'Полив и насос раствора заблокированы: уровень раствора ниже минимума.',
}

export const MANUAL_COMMAND_REJECTION_CODES = Object.keys(MANUAL_COMMAND_REJECTION_MESSAGES)

function normalizeRejectionCode(code?: string | null): string {
  return String(code ?? '').trim().toLowerCase().replace(/[^a-z0-9_-]/g, '_')
}

export function describeManualCommandRejection(code?: string | null): string | null {
  const normalized = normalizeRejectionCode(code)
  if (!normalized) return null
  return MANUAL_COMMAND_REJECTION_MESSAGES[normalized] ?? null
}
