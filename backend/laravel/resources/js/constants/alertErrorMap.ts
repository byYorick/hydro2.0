export type AlertSeverity = 'info' | 'warning' | 'error' | 'critical'

export interface AlertCodeMeta {
  title: string
  description: string
  recommendation?: string
  severity: AlertSeverity
}

const DEFAULT_ALERT_META: AlertCodeMeta = {
  title: 'Системное предупреждение',
  description: 'Сервис сообщил о состоянии, которое требует проверки.',
  recommendation: 'Проверьте детали алерта и журналы сервиса.',
  severity: 'warning',
}

const ALERT_CODE_MAP: Record<string, AlertCodeMeta> = {
  infra_command_send_failed: {
    title: 'Команда не отправлена',
    description: 'Команда управления не дошла до исполнительного узла.',
    recommendation: 'Проверьте привязку ноды, MQTT и доступность history-logger.',
    severity: 'critical',
  },
  infra_command_timeout: {
    title: 'Таймаут выполнения команды',
    description: 'Команда отправлена, но подтверждение не получено вовремя.',
    recommendation: 'Проверьте связь с узлом и его состояние в зоне.',
    severity: 'critical',
  },
  infra_command_failed: {
    title: 'Команда завершилась ошибкой',
    description: 'Исполнитель вернул статус ошибки.',
    recommendation: 'Откройте детали алерта и проверьте конкретную команду.',
    severity: 'error',
  },
  infra_command_invalid: {
    title: 'Команда отклонена',
    description: 'Команда не прошла проверку на стороне исполнителя.',
    recommendation: 'Проверьте параметры команды и конфигурацию каналов.',
    severity: 'error',
  },
  infra_command_busy: {
    title: 'Узел занят',
    description: 'Исполнитель временно не может принять команду.',
    recommendation: 'Повторите позже или проверьте очередь команд.',
    severity: 'warning',
  },
  infra_scheduler_command_failed: {
    title: 'Ошибка команды по расписанию',
    description: 'Планировщик не смог выполнить команду.',
    recommendation: 'Проверьте automation-engine и корректность расписания.',
    severity: 'error',
  },
  infra_scheduler_command_timeout: {
    title: 'Таймаут команды планировщика',
    description: 'Планировщик не дождался ответа automation-engine.',
    recommendation: 'Проверьте доступность automation-engine.',
    severity: 'critical',
  },
  infra_zone_processing_failed: {
    title: 'Ошибка обработки зоны',
    description: 'Automation Engine не смог обработать одну из зон.',
    recommendation: 'Проверьте телеметрию, конфигурацию и привязку устройств зоны.',
    severity: 'error',
  },
  infra_zone_failure_rate_high: {
    title: 'Высокий процент ошибок зон',
    description: 'Слишком много зон завершаются ошибкой в одном цикле.',
    recommendation: 'Проверьте состояние инфраструктуры и ключевых сервисов.',
    severity: 'critical',
  },
  infra_controller_failed: {
    title: 'Сбой контроллера автоматики',
    description: 'Один из контроллеров (климат/полив/свет/коррекция) завершился ошибкой.',
    recommendation: 'Проверьте детали контроллера и входную телеметрию.',
    severity: 'error',
  },
  infra_fill_mode_failed: {
    title: 'Ошибка режима Fill',
    description: 'Не удалось выполнить наполнение бака/контура.',
    recommendation: 'Проверьте узел воды, клапаны и датчики уровня.',
    severity: 'error',
  },
  infra_drain_mode_failed: {
    title: 'Ошибка режима Drain',
    description: 'Не удалось выполнить слив в заданный уровень.',
    recommendation: 'Проверьте дренажный канал и датчики уровня.',
    severity: 'error',
  },
  infra_flow_calibration_failed: {
    title: 'Ошибка калибровки расхода',
    description: 'Калибровка расхода воды завершилась ошибкой.',
    recommendation: 'Проверьте подключение датчика и насосного канала.',
    severity: 'error',
  },
  infra_automation_loop_error: {
    title: 'Ошибка цикла автоматики',
    description: 'Основной цикл automation-engine завершился исключением.',
    recommendation: 'Проверьте логи automation-engine и доступность БД/API.',
    severity: 'critical',
  },
  infra_unknown_error: {
    title: 'Неизвестная ошибка сервиса',
    description: 'Сервис вернул необработанное исключение.',
    recommendation: 'Откройте детали алерта и журналы сервиса.',
    severity: 'error',
  },
}

function normalizeCode(code?: string): string {
  return String(code || '').trim().toLowerCase()
}

export function resolveAlertCodeMeta(code?: string): AlertCodeMeta {
  const normalized = normalizeCode(code)
  if (normalized && ALERT_CODE_MAP[normalized]) {
    return ALERT_CODE_MAP[normalized]
  }

  if (normalized.startsWith('node_error_')) {
    return {
      title: 'Ошибка узла',
      description: 'Узел сообщил об ошибке оборудования или канала.',
      recommendation: 'Проверьте узел, питание и канал в деталях алерта.',
      severity: 'error',
    }
  }

  return DEFAULT_ALERT_META
}

export function resolveAlertSeverity(
  code?: string,
  details?: Record<string, unknown> | null,
): AlertSeverity {
  const rawSeverity = String(details?.severity || details?.level || '').trim().toLowerCase()
  if (rawSeverity === 'critical') return 'critical'
  if (rawSeverity === 'error') return 'error'
  if (rawSeverity === 'warning') return 'warning'
  if (rawSeverity === 'info') return 'info'
  return resolveAlertCodeMeta(code).severity
}

