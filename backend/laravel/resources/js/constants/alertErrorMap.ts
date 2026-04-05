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
  infra_controller_cooldown_skip: {
    title: 'Контроллер в паузе после сбоя',
    description: 'Контроллер временно пропущен из-за cooldown после ошибки.',
    recommendation: 'Проверьте причину исходной ошибки контроллера и повторите после паузы.',
    severity: 'warning',
  },
  infra_zone_backoff_skip: {
    title: 'Зона пропущена по backoff',
    description: 'Automation Engine временно не обрабатывает зону из-за серии ошибок.',
    recommendation: 'Откройте детали зоны и устраните первичную ошибку обработки.',
    severity: 'warning',
  },
  infra_zone_degraded_mode: {
    title: 'Зона в деградированном режиме',
    description: 'Выполняются только safety-проверки и health-мониторинг.',
    recommendation: 'Проверьте контроллеры зоны и восстановите нормальную обработку.',
    severity: 'error',
  },
  infra_zone_targets_missing: {
    title: 'Пропуск зоны без targets',
    description: 'У активного цикла отсутствуют или некорректны цели управления.',
    recommendation: 'Проверьте активный цикл выращивания и структуру targets.',
    severity: 'warning',
  },
  infra_zone_data_unavailable: {
    title: 'Недоступны данные зоны',
    description: 'Открыт DB circuit breaker, чтение данных зоны недоступно.',
    recommendation: 'Проверьте базу данных, сетевую доступность и состояние circuit breaker.',
    severity: 'critical',
  },
  infra_db_circuit_open: {
    title: 'Открыт circuit breaker базы данных',
    description: 'Главный цикл автоматики временно пропускает обработку зон.',
    recommendation: 'Проверьте состояние PostgreSQL и подключение automation-engine к БД.',
    severity: 'critical',
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
  sensor_state_inconsistent: {
    title: 'Несогласованное состояние датчиков',
    description: 'Комбинация min/max датчиков уровня противоречит логике бака.',
    recommendation: 'Проверьте wiring датчиков уровня и соответствие каналов ноды.',
    severity: 'error',
  },
  manual_ack_required_after_retries: {
    title: 'Требуется ручное подтверждение',
    description: 'Автопопытки исчерпаны, workflow ожидает подтверждение оператора.',
    recommendation: 'Проверьте причину остановки и подтвердите продолжение в UI.',
    severity: 'warning',
  },
  irr_state_unavailable: {
    title: 'Нет снимка состояния IRR',
    description: 'Не найден снимок состояния IRR-ноды для сверки ожидаемого и фактического состояния.',
    recommendation: 'Проверьте канал state на irr-ноде и поток command_response в history-logger.',
    severity: 'error',
  },
  irr_state_stale: {
    title: 'Снимок состояния IRR устарел',
    description: 'Снимок состояния irr-ноды старше допустимого окна свежести.',
    recommendation: 'Проверьте частоту опроса state и доставку ответов от irr-ноды.',
    severity: 'error',
  },
  irr_state_mismatch: {
    title: 'Состояние irr-ноды не совпало',
    description: 'Фактическое состояние клапанов/помпы не соответствует ожидаемому на critical этапе.',
    recommendation: 'Проверьте interlock клапанов/помпы и последовательность команд.',
    severity: 'error',
  },
  two_tank_irr_state_unavailable: {
    title: 'Нет снимка состояния IRR',
    description: 'Не найден снимок состояния irr-ноды для критической проверки двухбакового workflow.',
    recommendation: 'Проверьте обработку команды state и сохранение IRR_STATE_SNAPSHOT.',
    severity: 'error',
  },
  two_tank_irr_state_stale: {
    title: 'Снимок состояния IRR устарел',
    description: 'Снимок состояния irr-ноды устарел для критической проверки двухбакового workflow.',
    recommendation: 'Проверьте latency от запроса state до записи snapshot в zone_events.',
    severity: 'error',
  },
  two_tank_irr_state_mismatch: {
    title: 'Критическое расхождение состояния IRR',
    description: 'Ожидаемое и фактическое состояние irr-ноды расходятся на критическом этапе.',
    recommendation: 'Проверьте wiring, логи команд и фактическое состояние реле/клапанов.',
    severity: 'error',
  },
  irrigation_correction_attempts_exhausted_continue_irrigation: {
    title: 'Коррекция исчерпала лимит попыток',
    description: 'Целевые значения не достигнуты в лимите итераций, полив продолжается по расписанию.',
    recommendation: 'Проверьте дозирующие каналы и параметры рецепта EC/pH.',
    severity: 'warning',
  },
  biz_irrigation_decision_skip: {
    title: 'Полив пропущен решением контроллера',
    description: 'Decision-controller полива решил пропустить текущий запуск.',
    recommendation: 'Проверьте reason_code в деталях алерта и входную телеметрию стратегии полива.',
    severity: 'info',
  },
  biz_irrigation_decision_degraded: {
    title: 'Разрешён деградированный полив',
    description: 'Decision-controller полива разрешил запуск в деградированном режиме.',
    recommendation: 'Проверьте reason_code в деталях алерта и состояние входных датчиков.',
    severity: 'warning',
  },
  biz_irrigation_decision_fail: {
    title: 'Decision-controller полива отклонил запуск',
    description: 'AE3 остановил запуск полива на этапе принятия решения.',
    recommendation: 'Проверьте strategy/reason_code в деталях алерта и конфигурацию automation profile зоны.',
    severity: 'error',
  },
  biz_irrigation_solution_min: {
    title: 'Сработал нижний уровень раствора',
    description: 'Во время полива датчик нижнего уровня раствора сообщил о нехватке раствора.',
    recommendation: 'Проверьте уровень раствора, датчик и причину просадки уровня в контуре.',
    severity: 'warning',
  },
  biz_irrigation_replay_exhausted: {
    title: 'Исчерпаны повторы полива',
    description: 'AE3 исчерпал бюджет повторов после повторных срабатываний нижнего уровня раствора.',
    recommendation: 'Проверьте наличие раствора, работу насосов и повторные срабатывания solution_min.',
    severity: 'error',
  },
  biz_irrigation_wait_ready_timeout: {
    title: 'Таймаут ожидания READY',
    description: 'Полив не дождался перехода зоны в состояние READY в допустимое время.',
    recommendation: 'Проверьте workflow_phase зоны, активный цикл и логи automation-engine.',
    severity: 'warning',
  },
  biz_irrigation_correction_exhausted: {
    title: 'Коррекция во время полива исчерпана',
    description: 'Попытки коррекции во время полива исчерпаны, полив продолжается без новых коррекций.',
    recommendation: 'Проверьте дозирующие каналы, калибровки и текущие pH/EC target.',
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
