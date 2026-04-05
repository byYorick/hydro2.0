import catalogJson from '@/constants/error_codes.json'

interface ErrorCatalogEntry {
  code: string
  title?: string
  message?: string
}

interface ErrorCatalogFile {
  codes?: ErrorCatalogEntry[]
}

export interface HumanErrorInput {
  code?: string | null
  message?: string | null
  humanMessage?: string | null
}

const catalog = (catalogJson as ErrorCatalogFile).codes ?? []

const ERROR_MESSAGE_BY_CODE = new Map<string, string>()
for (const entry of catalog) {
  const code = normalizeErrorCode(entry?.code)
  const message = typeof entry?.message === 'string' ? entry.message.trim() : ''
  if (code && message) {
    ERROR_MESSAGE_BY_CODE.set(code, message)
  }
}

const RAW_MESSAGE_TRANSLATIONS: Record<string, string> = {
  'Intent skipped: zone busy': 'Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.',
  'Task execution exceeded runtime timeout': 'Выполнение задачи превысило допустимый runtime timeout.',
  'Zone lease was lost during task execution': 'Во время выполнения задачи был потерян lease зоны.',
  'IRR state snapshot unavailable': 'Снимок состояния IRR-ноды недоступен.',
  'IRR state snapshot stale': 'Снимок состояния IRR-ноды устарел.',
  'Irrigation decision-controller decided to skip irrigation.': 'Decision-controller полива решил пропустить запуск полива.',
  'Irrigation decision-controller allowed degraded irrigation run.': 'Decision-controller полива разрешил деградированный запуск полива.',
  'Irrigation decision-controller returned fail.': 'Decision-controller полива вернул отказ.',
  'Irrigation decision-controller returned fail': 'Decision-controller полива вернул отказ.',
  'Solution min level switch triggered during irrigation.': 'Во время полива сработал нижний датчик уровня раствора.',
  'Irrigation replay budget exhausted after repeated solution-min triggers.': 'Исчерпан бюджет повторных запусков после повторных срабатываний нижнего уровня раствора.',
  'Solution min triggered again after setup replay budget was exhausted': 'Нижний уровень раствора снова сработал после исчерпания бюджета повторов этапа setup.',
  'Irrigation task timed out in await_ready (zone_workflow_phase never became ready).': 'Полив превысил время ожидания на этапе await_ready: зона так и не перешла в состояние READY.',
  'Irrigation request timed out while waiting for READY state': 'Истекло время ожидания перехода зоны в состояние READY перед поливом.',
  'Irrigation recovery timeout exceeded': 'Превышено время этапа восстановления после полива.',
  'Prepare recirculation retry limit reached': 'Исчерпан лимит повторов подготовки рециркуляции.',
  "CycleStartPlanner requires zone.automation_runtime='ae3'": 'CycleStartPlanner требует, чтобы zone.automation_runtime был равен `ae3`.',
  'CycleStartPlanner requires an active grow_cycle with current_phase_id': 'CycleStartPlanner требует активный grow_cycle с заполненным current_phase_id.',
  'command_plans.plans.diagnostics is required': 'В automation bundle обязателен раздел command_plans.plans.diagnostics.',
  'diagnostics execution topology is required': 'Для diagnostics execution обязательно указать topology.',
  'command_plans.plans.diagnostics.steps must be a non-empty array': 'command_plans.plans.diagnostics.steps должен быть непустым массивом.',
  "lighting_tick requires zone.automation_runtime='ae3'": 'Для lighting_tick требуется zone.automation_runtime=`ae3`.',
  'lighting_tick requires at least one online actuator mapping in zone snapshot': 'Для lighting_tick требуется хотя бы один online actuator mapping в snapshot зоны.',
  'lighting_tick: no lighting actuator channel found (e.g. light_main)': 'Для lighting_tick не найден lighting actuator channel, например `light_main`.',
  'PlannedCommand payload must contain cmd and params': 'PlannedCommand должен содержать `cmd` и `params`.',
  'PlannedCommand payload must contain cmd and params for publish': 'Для публикации PlannedCommand должен содержать `cmd` и `params`.',
  'EC dose sequence JSON must be a list': 'JSON последовательности дозирования EC должен быть списком.',
  'EC dose sequence JSON is invalid': 'JSON последовательности дозирования EC некорректен.',
  'EC dose sequence item must be object': 'Элемент последовательности дозирования EC должен быть объектом.',
  'EC dose sequence missing node_uid': 'В последовательности дозирования EC отсутствует node_uid.',
  'EC dose sequence missing channel': 'В последовательности дозирования EC отсутствует channel.',
  'EC dose sequence amount_ml must be > 0': 'В последовательности дозирования EC поле amount_ml должно быть больше 0.',
  'Execution not found': 'Запрошенное выполнение не найдено.',
  'Command not found': 'Запрошенная команда не найдена.',
  'Access denied': 'У вас нет прав для доступа к этому объекту.',
  'Authentication required': 'Для выполнения действия нужно войти в систему.',
  Unauthorized: 'Для выполнения действия нужно войти в систему.',
  Forbidden: 'У вас нет прав для выполнения этого действия.',
  'Not found': 'Запрошенный объект не найден.',
  'Validation failed': 'Проверьте корректность переданных данных.',
  TIMEOUT: 'Превышено время ожидания выполнения команды.',
  SEND_FAILED: 'Команду не удалось отправить до узла.',
}

const RAW_MESSAGE_PATTERNS: Array<[RegExp, string]> = [
  [
    /^Zone (\d+) has no online actuator channels$/i,
    'В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.',
  ],
  [
    /^Intent skipped: zone busy(?: \(zone_id=(\d+)\))?$/i,
    'Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.',
  ],
  [
    /^Task execution exceeded (\d+)s timeout$/i,
    'Выполнение задачи превысило настроенный timeout.',
  ],
  [
    /^Task (\d+) has no claimed_by during startup recovery$/i,
    'Во время startup recovery у задачи отсутствует claimed_by.',
  ],
  [
    /^Task (\d+) has no confirmed external command during startup recovery$/i,
    'Во время startup recovery у задачи не подтверждена внешняя команда.',
  ],
  [
    /^Task (\d+) is waiting_command without resolvable legacy command$/i,
    'Задача находится в waiting_command без разрешимой legacy-команды.',
  ],
  [
    /^Unknown stage ([a-z0-9_-]+) in topology ([a-z0-9_-]+)$/i,
    'AE3 обнаружил неизвестный stage для указанной topology.',
  ],
  [
    /^Task (\d+) could not transition to completed$/i,
    'Не удалось перевести задачу в состояние completed.',
  ],
  [
    /^Task (\d+) could not transition to ([a-z0-9_-]+)$/i,
    'Не удалось перевести задачу на следующий stage.',
  ],
  [
    /^Task (\d+) has no ae_command for recovery$/i,
    'У задачи отсутствует связанная ae_command для recovery.',
  ],
  [
    /^Task (\d+) missing during ae_commands insert \(likely concurrent cleanup\)$/i,
    'Задача исчезла во время вставки в ae_commands, вероятно из-за конкурентного cleanup.',
  ],
  [
    /^Task (\d+) missing after HL publish while linking ae_commands \(likely concurrent cleanup\); cmd_id=(.+)$/i,
    'Задача исчезла после публикации через history-logger при связывании ae_commands.',
  ],
  [
    /^Task (\d+) missing before waiting_command transition \(likely concurrent cleanup\); cmd_id=(.+)$/i,
    'Задача исчезла перед переходом в waiting_command.',
  ],
  [
    /^Task (\d+) missing during publish pipeline \(likely concurrent cleanup\): (.+)$/i,
    'Задача исчезла во время publish pipeline.',
  ],
  [
    /^Task (\d+) became ([a-z_]+) during command roundtrip$/i,
    'Во время command roundtrip задача перешла в terminal-состояние.',
  ],
  [
    /^Task (\d+) could not enter waiting_command$/i,
    'Не удалось перевести задачу в waiting_command.',
  ],
  [
    /^Task (\d+) could not fail on ([A-Z_]+)$/i,
    'Не удалось перевести задачу в failed после terminal status.',
  ],
  [
    /^Command polling exceeded stage deadline for task (\d+) stage=(.+)$/i,
    'Опрос команды превысил дедлайн этапа.',
  ],
  [
    /^Command terminal status ([A-Z_]+)$/i,
    'Команда завершилась terminal status.',
  ],
  [
    /^Legacy commands\.id not found for zone_id=(\d+) cmd_id=(.+)$/i,
    'Не найдена запись legacy commands.id для зоны и cmd_id.',
  ],
  [
    /^Unsupported legacy status=(.+)$/i,
    'AE3 получил неподдерживаемый legacy-статус команды.',
  ],
  [
    /^ae_command (.+) has neither external_id nor payload\.cmd_id$/i,
    'У ae_command отсутствуют и external_id, и payload.cmd_id.',
  ],
  [
    /^Unable to move task_id=(\d+) into waiting_command$/i,
    'Не удалось перевести задачу в waiting_command.',
  ],
  [
    /^Unable to fail task_id=(\d+) after publish error$/i,
    'Не удалось перевести задачу в failed после ошибки публикации.',
  ],
  [
    /^Unable to recover task_id=(\d+) into waiting_command$/i,
    'Не удалось восстановить задачу в waiting_command.',
  ],
  [
    /^Unsupported startup recovery outcome=(.+)$/i,
    'Неподдерживаемый результат startup recovery.',
  ],
  [
    /^Unsupported native recovery state=(.+)$/i,
    'Неподдерживаемое состояние native recovery.',
  ],
  [
    /^Unsupported task_type for CycleStartPlanner: (.+)$/i,
    'CycleStartPlanner не поддерживает указанный task_type.',
  ],
  [
    /^AutomationTask\.zone_id=(\d+) does not match ZoneSnapshot\.zone_id=(\d+)$/i,
    'AutomationTask.zone_id не совпадает с ZoneSnapshot.zone_id.',
  ],
  [
    /^Unsupported command_plans\.schema_version=(.+)$/i,
    'Неподдерживаемая версия command_plans.schema_version.',
  ],
  [
    /^Unsupported diagnostics workflow for cycle_start planner: (.+)$/i,
    'CycleStartPlanner не поддерживает указанный diagnostics workflow.',
  ],
  [
    /^Invalid command plan step at index=(\d+)$/i,
    'Некорректный шаг command plan.',
  ],
  [
    /^Each command step must define channel\/cmd\/params \(index=(\d+)\)$/i,
    'Каждый шаг command plan должен содержать channel/cmd/params.',
  ],
  [
    /^Ambiguous system channel resolution for node_type=(.+)$/i,
    'Неоднозначное разрешение system channel для node_type.',
  ],
  [
    /^Expected exactly one runtime node for node_types=(.+)$/i,
    'Ожидалась ровно одна runtime-нода для указанных node_types.',
  ],
  [
    /^Missing required correction_config field: (.+)$/i,
    'Отсутствует обязательное поле correction_config.',
  ],
  [
    /^Missing or invalid correction_config field: (.+)$/i,
    'Поле correction_config отсутствует или некорректно.',
  ],
  [
    /^correction_config field (.+) must be >= (.+), got (.+)$/i,
    'Поле correction_config меньше допустимого значения.',
  ],
  [
    /^correction_config field (.+) must be <= (.+), got (.+)$/i,
    'Поле correction_config превышает допустимое значение.',
  ],
]

export function normalizeErrorCode(code?: string | null): string {
  const normalized = String(code ?? '').trim().toLowerCase()
  if (!normalized) return ''
  return normalized.replace(/[^a-z0-9_-]/g, '_')
}

export function isLocalizedErrorMessage(message?: string | null): boolean {
  return /[А-Яа-яЁё]/u.test(String(message ?? ''))
}

export function resolveHumanErrorMessage(input: HumanErrorInput, fallback?: string | null): string | null {
  const humanMessage = typeof input.humanMessage === 'string' ? input.humanMessage.trim() : ''
  if (humanMessage) {
    return humanMessage
  }

  const message = typeof input.message === 'string' ? input.message.trim() : ''
  if (message && isLocalizedErrorMessage(message)) {
    return message
  }

  const normalizedCode = normalizeErrorCode(input.code)
  if (normalizedCode && ERROR_MESSAGE_BY_CODE.has(normalizedCode)) {
    return ERROR_MESSAGE_BY_CODE.get(normalizedCode) ?? null
  }

  if (message && RAW_MESSAGE_TRANSLATIONS[message]) {
    return RAW_MESSAGE_TRANSLATIONS[message]
  }

  if (message) {
    for (const [pattern, translation] of RAW_MESSAGE_PATTERNS) {
      if (pattern.test(message)) {
        return translation
      }
    }
  }

  if (normalizedCode) {
    return `Внутренняя ошибка системы (код: ${normalizedCode}).`
  }

  if (message) {
    return fallback ?? 'Произошла ошибка сервиса. Проверьте логи и повторите попытку.'
  }

  return fallback ?? null
}
