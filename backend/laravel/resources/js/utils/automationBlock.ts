import type { Alert } from '@/types/Alert'

/**
 * Набор кодов алертов, которые означают «AE3 не возобновит автоматику без
 * ручного вмешательства» (AlertPolicyService::POLICY_MANAGED_CODES).
 *
 * Backend `UnifiedDashboardService::getAutomationBlockByZone` использует тот
 * же whitelist через `AlertPolicyService::policyManagedCodes()`, чтобы выдать
 * `automation_block` в payload дашборда. На странице зоны (`Zones/Show.vue`)
 * мы вычисляем такой же признак из массива `alerts` через `computeAutomationBlock`.
 */
export const POLICY_MANAGED_CODES = [
  'biz_ae3_task_failed',
  'biz_prepare_recirculation_retry_exhausted',
  'biz_correction_exhausted',
  'biz_ph_correction_no_effect',
  'biz_ec_correction_no_effect',
  'biz_zone_correction_config_missing',
  'biz_zone_dosing_calibration_missing',
  'biz_zone_pid_config_missing',
  'biz_zone_recipe_phase_targets_missing',
] as const

export interface AutomationBlockPayload {
  blocked: boolean
  reason_code: string | null
  severity: string | null
  message: string | null
  since: string | null
  alert_id: number | null
  alerts_count: number
}

interface ReasonMeta {
  label: string
  hint: string
}

const REASON_META: Record<string, ReasonMeta> = {
  biz_ae3_task_failed: {
    label: 'Задача AE3 завершилась ошибкой',
    hint: 'Запуск цикла или полива остановлен. Подтвердите алерт, чтобы запустить заново.',
  },
  biz_prepare_recirculation_retry_exhausted: {
    label: 'Не удалось подготовить рециркуляцию',
    hint: 'Исчерпаны попытки prepare_recirculation. Проверьте насосы и уровни баков.',
  },
  biz_correction_exhausted: {
    label: 'Исчерпаны попытки коррекции',
    hint: 'AE3 не смог свести pH/EC в коридор. Проверьте калибровки и состояние насосов.',
  },
  biz_ph_correction_no_effect: {
    label: 'Коррекция pH без эффекта',
    hint: 'Дозы pH не дают изменения. Проверьте сенсор pH, кислотный/щелочной насосы и реагенты.',
  },
  biz_ec_correction_no_effect: {
    label: 'Коррекция EC без эффекта',
    hint: 'Дозы EC не дают изменения. Проверьте сенсор EC, насосы A/B/C/D и канистры.',
  },
  biz_zone_correction_config_missing: {
    label: 'Не задана конфигурация коррекции',
    hint: 'У зоны отсутствует zone.correction. Заполните конфиг коррекции и попробуйте снова.',
  },
  biz_zone_dosing_calibration_missing: {
    label: 'Не выполнена калибровка дозирующих насосов',
    hint: 'Откройте настройки зоны и выполните калибровку pump_calibration.',
  },
  biz_zone_pid_config_missing: {
    label: 'Не задана конфигурация PID',
    hint: 'У зоны отсутствует zone.pid. Заполните параметры PID для контроллеров.',
  },
  biz_zone_recipe_phase_targets_missing: {
    label: 'В фазе рецепта нет targets',
    hint: 'У активной фазы рецепта отсутствуют pH/EC targets. Проверьте рецепт.',
  },
}

const FALLBACK_META: ReasonMeta = {
  label: 'Автоматика остановлена ошибкой',
  hint: 'Откройте вкладку «Алерты» зоны, чтобы увидеть подробности и подтвердить алерт.',
}

export function isAutomationBlockingCode(code?: string | null): boolean {
  if (!code) return false
  return (POLICY_MANAGED_CODES as readonly string[]).includes(String(code).toLowerCase().trim())
}

export function automationBlockLabel(code: string | null | undefined): string {
  if (!code) return FALLBACK_META.label
  const normalized = code.toLowerCase().trim()
  return REASON_META[normalized]?.label ?? FALLBACK_META.label
}

export function automationBlockHint(code: string | null | undefined): string {
  if (!code) return FALLBACK_META.hint
  const normalized = code.toLowerCase().trim()
  return REASON_META[normalized]?.hint ?? FALLBACK_META.hint
}

const SEVERITY_WEIGHT: Record<string, number> = {
  critical: 4,
  error: 3,
  warning: 2,
  info: 1,
}

/**
 * Вычисляет AutomationBlockPayload из массива алертов зоны
 * (используется на странице `Zones/Show.vue`, где payload приходит как `alerts`).
 *
 * Возвращает `null`, если ни один ACTIVE алерт не входит в whitelist.
 */
type AlertLike = Pick<Alert, 'id' | 'code' | 'severity' | 'status' | 'created_at' | 'details'> & {
  first_seen_at?: string | null
}

export function computeAutomationBlock(alerts: AlertLike[] | null | undefined): AutomationBlockPayload | null {
  if (!alerts?.length) return null

  let primary: AlertLike | null = null
  let count = 0

  for (const alert of alerts) {
    const status = String(alert.status ?? '').trim().toUpperCase()
    if (status !== 'ACTIVE') continue
    if (!isAutomationBlockingCode(alert.code)) continue

    count += 1
    const currentWeight = primary
      ? SEVERITY_WEIGHT[String(primary.severity ?? '').toLowerCase()] ?? 0
      : -1
    const candidateWeight = SEVERITY_WEIGHT[String(alert.severity ?? '').toLowerCase()] ?? 0
    if (!primary || candidateWeight > currentWeight) {
      primary = alert
    }
  }

  if (!primary || count === 0) return null

  const details = (primary.details ?? null) as Record<string, unknown> | null
  let message: string | null = null
  if (details && typeof details === 'object') {
    for (const key of ['human_error_message', 'message', 'error_message', 'reason'] as const) {
      const candidate = details[key]
      if (typeof candidate === 'string' && candidate.trim()) {
        message = candidate.trim()
        break
      }
    }
  }

  return {
    blocked: true,
    reason_code: primary.code ?? null,
    severity: primary.severity ?? null,
    message,
    since: primary.first_seen_at ?? primary.created_at ?? null,
    alert_id: primary.id ?? null,
    alerts_count: count,
  }
}
