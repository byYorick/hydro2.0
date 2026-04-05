<?php

namespace App\Services;

use Illuminate\Support\Facades\Log;

class ErrorCodeCatalogService
{
    /**
     * @var array<int, array<string, mixed>>|null
     */
    private static ?array $cachedCodes = null;

    /**
     * @var array<string, array<string, mixed>>|null
     */
    private static ?array $cachedByCode = null;

    /**
     * @return array{code:?string,title:string,message:?string}
     */
    public function present(?string $code, ?string $message = null): array
    {
        $normalizedCode = $this->normalizeCode($code);
        $entry = $normalizedCode !== '' ? ($this->codesByCode()[$normalizedCode] ?? null) : null;

        return [
            'code' => $normalizedCode !== '' ? $normalizedCode : null,
            'title' => is_array($entry) && is_string($entry['title'] ?? null) && trim($entry['title']) !== ''
                ? trim((string) $entry['title'])
                : 'Системная ошибка',
            'message' => $this->resolveMessage($normalizedCode, $message, $entry),
        ];
    }

    public function normalizeCode(?string $code): string
    {
        $normalized = strtolower(trim((string) ($code ?? '')));
        if ($normalized === '') {
            return '';
        }

        return preg_replace('/[^a-z0-9_\-]/', '_', $normalized) ?? $normalized;
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    private function codesByCode(): array
    {
        if (self::$cachedByCode !== null) {
            return self::$cachedByCode;
        }

        $this->loadCatalog();

        return self::$cachedByCode ?? [];
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    private function loadCatalog(): array
    {
        if (self::$cachedCodes !== null) {
            return self::$cachedCodes;
        }

        $candidatePaths = [
            base_path('error_codes.json'),
            base_path('../error_codes.json'),
            base_path('../../error_codes.json'),
        ];

        $path = null;
        foreach ($candidatePaths as $candidatePath) {
            if (is_file($candidatePath)) {
                $path = $candidatePath;
                break;
            }
        }

        if (! is_string($path)) {
            Log::warning('Error code catalog file not found', ['paths' => $candidatePaths]);
            self::$cachedCodes = [];
            self::$cachedByCode = [];

            return [];
        }

        $raw = file_get_contents($path);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        $codes = is_array($decoded['codes'] ?? null) ? $decoded['codes'] : [];

        $normalizedCodes = [];
        $byCode = [];

        foreach ($codes as $row) {
            if (! is_array($row)) {
                continue;
            }

            $normalizedCode = $this->normalizeCode($row['code'] ?? null);
            if ($normalizedCode === '') {
                continue;
            }

            $normalizedRow = [
                'code' => $normalizedCode,
                'title' => trim((string) ($row['title'] ?? '')),
                'message' => trim((string) ($row['message'] ?? '')),
            ];

            $normalizedCodes[] = $normalizedRow;
            $byCode[$normalizedCode] = $normalizedRow;
        }

        self::$cachedCodes = $normalizedCodes;
        self::$cachedByCode = $byCode;

        return $normalizedCodes;
    }

    /**
     * @param  array<string, mixed>|null  $entry
     */
    private function resolveMessage(string $code, ?string $message, ?array $entry): ?string
    {
        $rawMessage = trim((string) ($message ?? ''));

        if ($rawMessage !== '' && $this->looksLocalized($rawMessage)) {
            return $rawMessage;
        }

        if (is_array($entry) && is_string($entry['message'] ?? null) && trim((string) $entry['message']) !== '') {
            return trim((string) $entry['message']);
        }

        if ($rawMessage !== '') {
            $translated = $this->translateRawMessage($rawMessage);
            if ($translated !== null) {
                return $translated;
            }
        }

        if ($code !== '') {
            return sprintf('Внутренняя ошибка системы (код: %s).', $code);
        }

        if ($rawMessage !== '') {
            return 'Произошла ошибка сервиса. Проверьте логи и повторите попытку.';
        }

        return null;
    }

    private function translateRawMessage(string $message): ?string
    {
        $exactMap = [
            'Intent skipped: zone busy' => 'Повторный запуск отклонён: зона уже занята активной задачей.',
            'Task execution exceeded runtime timeout' => 'Выполнение задачи превысило допустимый runtime timeout.',
            'Zone lease was lost during task execution' => 'Во время выполнения задачи был потерян lease зоны.',
            'IRR state snapshot unavailable' => 'Снимок состояния IRR-ноды недоступен.',
            'IRR state snapshot stale' => 'Снимок состояния IRR-ноды устарел.',
            'Irrigation decision-controller decided to skip irrigation.' => 'Decision-controller полива решил пропустить запуск полива.',
            'Irrigation decision-controller allowed degraded irrigation run.' => 'Decision-controller полива разрешил деградированный запуск полива.',
            'Irrigation decision-controller returned fail.' => 'Decision-controller полива вернул отказ.',
            'Irrigation decision-controller returned fail' => 'Decision-controller полива вернул отказ.',
            'Solution min level switch triggered during irrigation.' => 'Во время полива сработал нижний датчик уровня раствора.',
            'Irrigation replay budget exhausted after repeated solution-min triggers.' => 'Исчерпан бюджет повторных запусков после повторных срабатываний нижнего уровня раствора.',
            'Solution min triggered again after setup replay budget was exhausted' => 'Нижний уровень раствора снова сработал после исчерпания бюджета повторов этапа setup.',
            'Irrigation task timed out in await_ready (zone_workflow_phase never became ready).' => 'Полив превысил время ожидания на этапе await_ready: зона так и не перешла в состояние READY.',
            'Irrigation request timed out while waiting for READY state' => 'Истекло время ожидания перехода зоны в состояние READY перед поливом.',
            'Irrigation recovery timeout exceeded' => 'Превышено время этапа восстановления после полива.',
            'Prepare recirculation retry limit reached' => 'Исчерпан лимит повторов подготовки рециркуляции.',
            'CycleStartPlanner requires zone.automation_runtime=\'ae3\'' => 'CycleStartPlanner требует, чтобы zone.automation_runtime был равен `ae3`.',
            'CycleStartPlanner requires an active grow_cycle with current_phase_id' => 'CycleStartPlanner требует активный grow_cycle с заполненным current_phase_id.',
            'command_plans.plans.diagnostics is required' => 'В automation bundle обязателен раздел command_plans.plans.diagnostics.',
            'diagnostics execution topology is required' => 'Для diagnostics execution обязательно указать topology.',
            'command_plans.plans.diagnostics.steps must be a non-empty array' => 'command_plans.plans.diagnostics.steps должен быть непустым массивом.',
            'lighting_tick requires zone.automation_runtime=\'ae3\'' => 'Для lighting_tick требуется zone.automation_runtime=`ae3`.',
            'lighting_tick requires at least one online actuator mapping in zone snapshot' => 'Для lighting_tick требуется хотя бы один online actuator mapping в snapshot зоны.',
            'lighting_tick: no lighting actuator channel found (e.g. light_main)' => 'Для lighting_tick не найден lighting actuator channel, например `light_main`.',
            'PlannedCommand payload must contain cmd and params' => 'PlannedCommand должен содержать `cmd` и `params`.',
            'PlannedCommand payload must contain cmd and params for publish' => 'Для публикации PlannedCommand должен содержать `cmd` и `params`.',
            'EC dose sequence JSON must be a list' => 'JSON последовательности дозирования EC должен быть списком.',
            'EC dose sequence JSON is invalid' => 'JSON последовательности дозирования EC некорректен.',
            'EC dose sequence item must be object' => 'Элемент последовательности дозирования EC должен быть объектом.',
            'EC dose sequence missing node_uid' => 'В последовательности дозирования EC отсутствует node_uid.',
            'EC dose sequence missing channel' => 'В последовательности дозирования EC отсутствует channel.',
            'EC dose sequence amount_ml must be > 0' => 'В последовательности дозирования EC поле amount_ml должно быть больше 0.',
            'Execution not found' => 'Запрошенное выполнение не найдено.',
            'Command not found' => 'Запрошенная команда не найдена.',
            'Access denied' => 'У вас нет прав для доступа к этому объекту.',
            'Authentication required' => 'Для выполнения действия нужно войти в систему.',
            'Unauthorized' => 'Для выполнения действия нужно войти в систему.',
            'Forbidden' => 'У вас нет прав для выполнения этого действия.',
            'Not found' => 'Запрошенный объект не найден.',
            'Validation failed' => 'Проверьте корректность переданных данных.',
            'TIMEOUT' => 'Превышено время ожидания выполнения команды.',
            'SEND_FAILED' => 'Команду не удалось отправить до узла.',
        ];

        if (isset($exactMap[$message])) {
            return $exactMap[$message];
        }

        if (preg_match('/^Zone \d+ has no online actuator channels$/i', $message) === 1) {
            return 'В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.';
        }

        if (preg_match('/^Intent skipped: zone busy(?: \(zone_id=(\d+)\))?$/i', $message, $matches) === 1) {
            $zoneId = isset($matches[1]) && $matches[1] !== '' ? (int) $matches[1] : null;
            return $zoneId !== null
                ? sprintf('Повторный запуск отклонён: зона %d уже занята активной задачей или intent.', $zoneId)
                : 'Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.';
        }

        if (preg_match('/^Task execution exceeded (\d+)s timeout$/i', $message, $matches) === 1) {
            return sprintf('Выполнение задачи превысило timeout %d с.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) has no claimed_by during startup recovery$/i', $message, $matches) === 1) {
            return sprintf('Во время startup recovery у задачи %d отсутствует claimed_by.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) has no confirmed external command during startup recovery$/i', $message, $matches) === 1) {
            return sprintf('Во время startup recovery у задачи %d не подтверждена внешняя команда.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) is waiting_command without resolvable legacy command$/i', $message, $matches) === 1) {
            return sprintf('Задача %d находится в waiting_command без разрешимой legacy-команды.', (int) $matches[1]);
        }

        if (preg_match('/^Unknown stage ([a-z0-9_\-]+) in topology ([a-z0-9_\-]+)$/i', $message, $matches) === 1) {
            return sprintf('Неизвестный stage %s для topology %s.', $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) could not transition to completed$/i', $message, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d в состояние completed.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) could not transition to ([a-z0-9_\-]+)$/i', $message, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d на stage %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) has no ae_command for recovery$/i', $message, $matches) === 1) {
            return sprintf('У задачи %d отсутствует связанная ae_command для recovery.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) missing during ae_commands insert \(likely concurrent cleanup\)$/i', $message, $matches) === 1) {
            return sprintf('Задача %d исчезла во время вставки в ae_commands, вероятно из-за конкурентного cleanup.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) missing after HL publish while linking ae_commands \(likely concurrent cleanup\); cmd_id=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Задача %d исчезла после публикации через history-logger при связывании ae_commands; cmd_id=%s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) missing before waiting_command transition \(likely concurrent cleanup\); cmd_id=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Задача %d исчезла перед переходом в waiting_command; cmd_id=%s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) missing during publish pipeline \(likely concurrent cleanup\): (.+)$/i', $message, $matches) === 1) {
            return sprintf('Задача %d исчезла во время publish pipeline: %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) became ([a-z_]+) during command roundtrip$/i', $message, $matches) === 1) {
            return sprintf('Во время command roundtrip задача %d перешла в состояние %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) could not enter waiting_command$/i', $message, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d в waiting_command.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) could not fail on ([A-Z_]+)$/i', $message, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d в failed после terminal status %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Command polling exceeded stage deadline for task (\d+) stage=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Опрос команды превысил дедлайн stage для задачи %d на этапе %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Command terminal status ([A-Z_]+)$/i', $message, $matches) === 1) {
            return sprintf('Команда завершилась terminal status %s.', $matches[1]);
        }

        if (preg_match('/^Legacy commands\.id not found for zone_id=(\d+) cmd_id=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Не найдена запись legacy commands.id для зоны %d и cmd_id=%s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Unsupported legacy status=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Неподдерживаемый legacy-статус: %s.', $matches[1]);
        }

        if (preg_match('/^ae_command (.+) has neither external_id nor payload\.cmd_id$/i', $message, $matches) === 1) {
            return sprintf('У ae_command %s отсутствуют и external_id, и payload.cmd_id.', $matches[1]);
        }

        if (preg_match('/^Unable to move task_id=(\d+) into waiting_command$/i', $message, $matches) === 1) {
            return sprintf('Не удалось перевести task_id=%d в waiting_command.', (int) $matches[1]);
        }

        if (preg_match('/^Unable to fail task_id=(\d+) after publish error$/i', $message, $matches) === 1) {
            return sprintf('Не удалось перевести task_id=%d в failed после ошибки публикации.', (int) $matches[1]);
        }

        if (preg_match('/^Unable to recover task_id=(\d+) into waiting_command$/i', $message, $matches) === 1) {
            return sprintf('Не удалось восстановить task_id=%d в состояние waiting_command.', (int) $matches[1]);
        }

        if (preg_match('/^Unsupported startup recovery outcome=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Неподдерживаемый результат startup recovery: %s.', $matches[1]);
        }

        if (preg_match('/^Unsupported native recovery state=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Неподдерживаемое состояние native recovery: %s.', $matches[1]);
        }

        if (preg_match('/^Unsupported task_type for CycleStartPlanner: (.+)$/i', $message, $matches) === 1) {
            return sprintf('CycleStartPlanner не поддерживает task_type=%s.', $matches[1]);
        }

        if (preg_match('/^AutomationTask\.zone_id=(\d+) does not match ZoneSnapshot\.zone_id=(\d+)$/i', $message, $matches) === 1) {
            return sprintf('AutomationTask.zone_id=%d не совпадает с ZoneSnapshot.zone_id=%d.', (int) $matches[1], (int) $matches[2]);
        }

        if (preg_match('/^Unsupported command_plans\.schema_version=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Неподдерживаемая версия command_plans.schema_version=%s.', $matches[1]);
        }

        if (preg_match('/^Unsupported diagnostics workflow for cycle_start planner: (.+)$/i', $message, $matches) === 1) {
            return sprintf('CycleStartPlanner не поддерживает diagnostics workflow=%s.', $matches[1]);
        }

        if (preg_match('/^Invalid command plan step at index=(\d+)$/i', $message, $matches) === 1) {
            return sprintf('Некорректный шаг command plan на позиции %d.', (int) $matches[1]);
        }

        if (preg_match('/^Each command step must define channel\/cmd\/params \(index=(\d+)\)$/i', $message, $matches) === 1) {
            return sprintf('Каждый шаг command plan должен содержать channel/cmd/params (index=%d).', (int) $matches[1]);
        }

        if (preg_match('/^Ambiguous system channel resolution for node_type=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Неоднозначное разрешение system channel для node_type=%s.', $matches[1]);
        }

        if (preg_match('/^Expected exactly one runtime node for node_types=(.+)$/i', $message, $matches) === 1) {
            return sprintf('Ожидалась ровно одна runtime-нода для node_types=%s.', $matches[1]);
        }

        if (preg_match('/^Missing required correction_config field: (.+)$/i', $message, $matches) === 1) {
            return sprintf('Отсутствует обязательное поле correction_config: %s.', $matches[1]);
        }

        if (preg_match('/^Missing or invalid correction_config field: (.+)$/i', $message, $matches) === 1) {
            return sprintf('Поле correction_config отсутствует или некорректно: %s.', $matches[1]);
        }

        if (preg_match('/^correction_config field (.+) must be >= (.+), got (.+)$/i', $message, $matches) === 1) {
            return sprintf('Поле correction_config %s должно быть >= %s, получено %s.', $matches[1], $matches[2], $matches[3]);
        }

        if (preg_match('/^correction_config field (.+) must be <= (.+), got (.+)$/i', $message, $matches) === 1) {
            return sprintf('Поле correction_config %s должно быть <= %s, получено %s.', $matches[1], $matches[2], $matches[3]);
        }

        return null;
    }

    private function looksLocalized(string $value): bool
    {
        return preg_match('/[А-Яа-яЁё]/u', $value) === 1;
    }
}
