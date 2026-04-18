<?php

declare(strict_types=1);

namespace App\Services\AlertLocalization;

use App\Services\AlertCatalogService;

/**
 * Переводит сообщение alert'а на русский по его business-коду.
 *
 * Работает в двух режимах:
 *  - известный код → фиксированный перевод (match в {@see translateByCode})
 *  - специализированные коды (AE3 task failure, correction no-effect, config-missing) → свои форматы
 *  - raw английские сообщения → exact-map + структурные regex (через {@see AlertStructuredMessageParser})
 */
class AlertCodeTranslator
{
    private const EXACT_MESSAGE_MAP = [
        'Correction cycle exhausted all configured attempts.' => 'Цикл коррекции исчерпал все настроенные попытки.',
        'Correction during irrigation exhausted all configured attempts.' => 'Попытки коррекции во время полива исчерпаны.',
        'Clean tank fill deadline exceeded after all retry cycles.' => 'Превышено время ожидания заполнения бака чистой водой после всех циклов повтора.',
        'Clean tank fill deadline exceeded after all retry cycles — check water supply.' => 'Превышено время ожидания заполнения бака чистой водой после всех циклов повтора; проверьте подачу воды.',
        'Solution tank fill deadline exceeded before the stage could complete.' => 'Превышено время ожидания заполнения бака раствором до завершения этапа.',
        'Solution tank fill deadline exceeded — check solution supply valve and pump.' => 'Превышено время ожидания заполнения бака раствором; проверьте клапан подачи раствора и насос.',
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
        'IRR state snapshot unavailable' => 'Снимок состояния IRR-ноды недоступен.',
        'IRR state snapshot stale' => 'Снимок состояния IRR-ноды устарел.',
        'Zone lease was lost during task execution' => 'Во время выполнения задачи был потерян lease зоны.',
        'Zone lease is no longer present after task completion.' => 'После завершения задачи lease зоны больше не присутствует.',
        'Zone lease could not be released after task completion.' => 'Не удалось освободить lease зоны после завершения задачи.',
        'Zone lease could not be released after task completion — zone may be locked.' => 'Не удалось освободить lease зоны после завершения задачи: зона могла остаться заблокированной.',
        'Zone lease heartbeat failed and the worker kept running without a valid lease.' => 'Потерян heartbeat lease зоны, и worker продолжил выполнение без действительной блокировки.',
        'Zone lease heartbeat failed to extend — zone may be hijacked or frozen.' => 'Не удалось продлить heartbeat lease зоны: зону могли перехватить или она зависла.',
        'Task execution exceeded runtime timeout' => 'Выполнение задачи превысило допустимый runtime timeout.',
        'Transition outcome requires next_stage' => 'Результат перехода требует указания next_stage.',
        'Unable to persist irrigation replay count' => 'Не удалось сохранить счётчик повторов полива.',
        'Unable to persist irrigation decision' => 'Не удалось сохранить решение decision-controller полива.',
        'idempotency_key is required' => 'Для запуска обязателен idempotency_key.',
        'history-logger returned invalid JSON' => 'history-logger вернул некорректный JSON.',
        'history-logger response does not contain data.command_id' => 'Ответ history-logger не содержит data.command_id.',
        "CycleStartPlanner requires zone.automation_runtime='ae3'" => 'CycleStartPlanner требует, чтобы zone.automation_runtime был равен `ae3`.',
        'CycleStartPlanner requires an active grow_cycle with current_phase_id' => 'CycleStartPlanner требует активный grow_cycle с заполненным current_phase_id.',
        'command_plans.plans.diagnostics is required' => 'В automation bundle обязателен раздел command_plans.plans.diagnostics.',
        'diagnostics execution topology is required' => 'Для diagnostics execution обязательно указать topology.',
        'command_plans.plans.diagnostics.steps must be a non-empty array' => 'command_plans.plans.diagnostics.steps должен быть непустым массивом.',
        "lighting_tick requires zone.automation_runtime='ae3'" => 'Для lighting_tick требуется zone.automation_runtime=`ae3`.',
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
    ];

    public function __construct(
        private AlertCatalogService $alertCatalogService,
        private AlertStructuredMessageParser $structuredParser,
        private DetailsAccessor $accessor,
    ) {}

    /**
     * @param array<string, mixed> $details
     */
    public function translateByCode(string $code, ?string $rawMessage, array $details): ?string
    {
        return match ($code) {
            'biz_ae3_task_failed' => $this->translateAe3TaskFailed($rawMessage, $details),
            'biz_correction_exhausted' => 'Цикл коррекции исчерпал все настроенные попытки.',
            'biz_clean_fill_timeout' => 'Превышено время ожидания заполнения бака чистой водой после всех циклов повтора.',
            'biz_solution_fill_timeout' => 'Превышено время ожидания заполнения бака раствором до завершения этапа.',
            'biz_irrigation_decision_skip' => $this->translateRawMessage($rawMessage ?? '') ?? 'Decision-controller полива решил пропустить запуск полива.',
            'biz_irrigation_decision_degraded' => $this->translateRawMessage($rawMessage ?? '') ?? 'Decision-controller полива разрешил деградированный запуск полива.',
            'biz_irrigation_decision_fail' => $this->translateRawMessage($rawMessage ?? '') ?? 'Decision-controller полива вернул отказ.',
            'biz_irrigation_solution_min' => $this->translateRawMessage($rawMessage ?? '') ?? 'Во время полива сработал нижний датчик уровня раствора.',
            'biz_irrigation_replay_exhausted' => $this->translateRawMessage($rawMessage ?? '') ?? 'Исчерпан бюджет повторных запусков после повторных срабатываний нижнего уровня раствора.',
            'biz_irrigation_wait_ready_timeout' => $this->translateRawMessage($rawMessage ?? '') ?? 'Полив не дождался перехода зоны в состояние READY.',
            'biz_irrigation_correction_exhausted' => $this->translateRawMessage($rawMessage ?? '') ?? 'Попытки коррекции во время полива исчерпаны; полив продолжится без новых попыток коррекции на этом этапе.',
            'irr_state_unavailable' => 'Снимок состояния IRR-ноды недоступен.',
            'irr_state_stale' => 'Снимок состояния IRR-ноды устарел.',
            'irr_state_mismatch' => $this->translateIrrStateMismatch($rawMessage) ?? 'Состояние IRR-ноды не совпадает с ожидаемым.',
            'two_tank_irr_state_unavailable' => 'Снимок состояния IRR-ноды недоступен для критической проверки двухбакового workflow.',
            'two_tank_irr_state_stale' => 'Снимок состояния IRR-ноды устарел для критической проверки двухбакового workflow.',
            'two_tank_irr_state_mismatch' => $this->translateIrrStateMismatch($rawMessage) ?? 'Состояние IRR-ноды не совпадает с ожидаемым на критическом этапе двухбакового workflow.',
            'ae3_zone_lease_release_failed' => 'Не удалось освободить lease зоны после завершения задачи.',
            'ae3_zone_lease_lost' => 'Worker потерял lease зоны и продолжил выполнение без действительной блокировки.',
            'ae3_background_task_crashed' => 'Фоновая задача AE3 завершилась с аварией.',
            'ae3_api_unhandled_exception' => 'AE3 API завершился необработанным исключением.',
            'infra_command_ack_command_not_found' => $rawMessage ?? 'Laravel не нашёл команду при обработке ACK.',
            'biz_zone_correction_config_missing', 'zone_correction_config_missing_critical' => $this->translateCorrectionConfigMissing($rawMessage),
            'biz_zone_pid_config_missing', 'zone_pid_config_missing_critical' => $this->translatePidConfigMissing($rawMessage),
            'biz_zone_recipe_phase_targets_missing', 'zone_recipe_phase_targets_missing_critical' => $this->translateRecipePhaseTargetsMissing($rawMessage),
            'biz_zone_dosing_calibration_missing', 'zone_dosing_calibration_missing_critical' => $this->translateDosingCalibrationMissing($rawMessage),
            'biz_ph_correction_no_effect', 'biz_ec_correction_no_effect' => $this->translateCorrectionNoEffect($rawMessage, $details),
            'ae3_api_http_5xx' => $this->translateAe3HttpMessage($rawMessage),
            default => null,
        };
    }

    public function translateRawMessage(string $message): ?string
    {
        $normalized = trim($message);
        if ($normalized === '') {
            return null;
        }

        if (array_key_exists($normalized, self::EXACT_MESSAGE_MAP)) {
            return self::EXACT_MESSAGE_MAP[$normalized];
        }

        return $this->translateCorrectionNoEffect($normalized, [])
            ?? $this->translateIrrStateMismatch($normalized)
            ?? $this->structuredParser->parse($normalized)
            ?? $this->translateAe3HttpMessage($normalized);
    }

    /**
     * @param array<string, mixed> $details
     */
    public function translateAe3TaskFailed(?string $message, array $details): string
    {
        $taskId = $this->accessor->scalarValue($details, ['task_id']);
        $taskType = $this->accessor->stringValue($details, ['task_type']);
        $stage = $this->accessor->stringValue($details, ['stage']);
        $workflowPhase = $this->accessor->stringValue($details, ['workflow_phase']);
        $topology = $this->accessor->stringValue($details, ['topology']);
        $corrStep = $this->accessor->stringValue($details, ['corr_step']);
        $retryCount = $this->accessor->integerValue($details, ['stage_retry_count']);

        $reasonCode = $this->alertCatalogService->normalizeCode($details['error_code'] ?? null);
        $reasonRaw = $this->accessor->stringValue($details, ['error_message', 'message', 'reason', 'msg']) ?? $message;
        $reason = null;

        if ($reasonCode === 'command_timeout') {
            $reason = $this->translateCommandTimeoutReason($details);
        }

        if ($reason === null && $reasonCode !== '' && $reasonCode !== 'biz_ae3_task_failed') {
            $reason = $this->translateByCode($reasonCode, $reasonRaw, $details);
        }

        if ($reason === null && $reasonRaw !== null) {
            $reason = $this->translateRawMessage($reasonRaw) ?? $reasonRaw;
        }

        if ($reason === null || trim($reason) === '') {
            $reason = 'Проверьте логи automation-engine для точной причины ошибки.';
        }

        $headline = 'Задача AE3';
        if ($taskId !== null) {
            $headline .= ' #'.$taskId;
        }
        if ($taskType !== null) {
            $headline .= sprintf(' (%s)', $taskType);
        }

        $context = [];
        if ($stage !== null) {
            $context[] = 'этап '.$stage;
        }
        if ($workflowPhase !== null && $workflowPhase !== $stage) {
            $context[] = 'workflow '.$workflowPhase;
        }
        if ($topology !== null) {
            $context[] = 'topology '.$topology;
        }
        if ($corrStep !== null) {
            $context[] = 'corr_step '.$corrStep;
        }
        if ($retryCount !== null && $retryCount > 0) {
            $context[] = 'retry '.$retryCount;
        }

        $summary = $headline.' завершилась с ошибкой';
        if ($reasonCode !== '') {
            $summary .= sprintf(' (код: %s)', $reasonCode);
        }
        $summary .= $context !== [] ? ': '.implode(', ', $context).'.' : '.';

        return $summary.' Причина: '.$reason;
    }

    /**
     * @param array<string, mixed> $details
     */
    private function translateCommandTimeoutReason(array $details): ?string
    {
        $timeoutDetails = $details['timed_out_command'] ?? $details['startup_probe_timeout'] ?? null;
        if (! is_array($timeoutDetails)) {
            return null;
        }

        $probeName = $this->accessor->stringValue($timeoutDetails, ['probe_name']);
        $cmdId = $this->accessor->stringValue($timeoutDetails, ['cmd_id']);
        $nodeUid = $this->accessor->stringValue($timeoutDetails, ['node_uid']);
        $channel = $this->accessor->stringValue($timeoutDetails, ['channel']);
        $nodeStatus = $this->accessor->stringValue($timeoutDetails, ['node_status']);
        $lastSeenAgeSec = $this->accessor->integerValue($timeoutDetails, ['node_last_seen_age_sec']);
        $staleCandidate = filter_var($timeoutDetails['node_stale_online_candidate'] ?? false, FILTER_VALIDATE_BOOL);

        $parts = [];
        if ($probeName !== null) {
            $parts[] = "probe {$probeName}";
        }
        if ($cmdId !== null) {
            $parts[] = "команда {$cmdId}";
        }
        if ($nodeUid !== null) {
            $parts[] = "нода {$nodeUid}";
        }
        if ($channel !== null) {
            $parts[] = "канал {$channel}";
        }

        $msg = $parts !== []
            ? 'Не дождались ответа: '.implode(', ', $parts).'.'
            : 'Команда не вернула ACK или terminal response до истечения timeout.';

        $context = [];
        if ($nodeStatus !== null) {
            $context[] = "статус узла {$nodeStatus}";
        }
        if ($lastSeenAgeSec !== null) {
            $context[] = "last_seen {$lastSeenAgeSec} с назад";
        }
        if ($staleCandidate) {
            $context[] = 'online-статус уже выглядел устаревшим';
        }

        if ($context !== []) {
            $msg .= ' Контекст: '.implode(', ', $context).'.';
        }

        return $msg;
    }

    public function translateIrrStateMismatch(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return null;
        }

        if (preg_match('/^IRR state mismatch for ([a-z0-9_\-]+): expected=(.+), got=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf(
                'Состояние IRR-ноды не совпало по признаку %s: ожидалось %s, получено %s.',
                $matches[1],
                $matches[2],
                $matches[3],
            );
        }

        return null;
    }

    private function translateCorrectionConfigMissing(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return 'В конфигурации коррекции отсутствуют обязательные поля; критические параметры коррекции переведены в fail-closed режим.';
        }

        if (preg_match('/^Zone (\d+) correction_config\.([a-z0-9_\-]+) missing required fields: (.+); fail-closed for critical correction parameters$/i', $normalized, $m) === 1) {
            return sprintf(
                'В зоне %d в correction_config.%s отсутствуют обязательные поля: %s; критические параметры коррекции переведены в fail-closed режим.',
                (int) $m[1],
                $m[2],
                $m[3],
            );
        }

        return null;
    }

    private function translatePidConfigMissing(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return 'Отсутствует обязательная PID-конфигурация зоны; критические параметры коррекции переведены в fail-closed режим.';
        }

        if (preg_match('/^Zone (\d+) missing required pid authority documents for pid_type=(.+); fail-closed for critical correction parameters$/i', $normalized, $m) === 1) {
            return sprintf(
                'В зоне %d отсутствуют обязательные PID authority-документы для pid_type=%s; критические параметры коррекции переведены в fail-closed режим.',
                (int) $m[1],
                $m[2],
            );
        }

        if (preg_match('/^Zone (\d+) has no pid authority mapping; fail-closed for critical correction parameters$/i', $normalized, $m) === 1) {
            return sprintf(
                'В зоне %d отсутствует mapping PID authority-конфига; критические параметры коррекции переведены в fail-closed режим.',
                (int) $m[1],
            );
        }

        return null;
    }

    private function translateRecipePhaseTargetsMissing(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return 'В актуальной фазе рецепта отсутствуют обязательные pH/EC target; automation переведена в fail-closed режим.';
        }

        if (preg_match('/^Zone (\d+) current recipe phase has no target_(ph|ec); automation requires recipe-phase pH\/EC targets and forbids defaults or runtime overrides$/i', $normalized, $m) === 1) {
            return sprintf(
                'В зоне %d в актуальной фазе рецепта отсутствует target_%s; automation переведена в fail-closed режим без defaults и runtime override.',
                (int) $m[1],
                strtolower($m[2]),
            );
        }

        if (preg_match('/^Zone (\d+) current recipe phase target_(ph|ec) is not numeric: (.+)$/i', $normalized, $m) === 1) {
            return sprintf(
                'В зоне %d в актуальной фазе рецепта target_%s имеет нечисловое значение: %s.',
                (int) $m[1],
                strtolower($m[2]),
                $m[3],
            );
        }

        return null;
    }

    private function translateDosingCalibrationMissing(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return 'Отсутствует обязательная калибровка дозирующего насоса.';
        }

        if (preg_match('/^(EC|PH) dosing pump calibration is required \(channel=([^,]+), node=([^)]+)\)$/i', $normalized, $m) === 1) {
            return sprintf(
                'Для %s требуется калибровка дозирующего насоса (channel=%s, node=%s).',
                strtoupper($m[1]),
                $m[2],
                $m[3],
            );
        }

        return null;
    }

    /**
     * @param array<string, mixed> $details
     */
    public function translateCorrectionNoEffect(?string $message, array $details): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            $pidType = strtoupper((string) ($details['pid_type'] ?? ''));
            $limit = isset($details['no_effect_limit']) ? (int) $details['no_effect_limit'] : null;
            if ($pidType !== '' && $limit !== null && $limit > 0) {
                return sprintf(
                    'Коррекция %s не дала наблюдаемого отклика %d раз подряд.',
                    $pidType,
                    $limit,
                );
            }

            return null;
        }

        if (preg_match('/^(PH|EC) correction produced no observable response (\d+) times in a row\.$/i', $normalized, $m) === 1) {
            return sprintf(
                'Коррекция %s не дала наблюдаемого отклика %d раз подряд.',
                strtoupper($m[1]),
                (int) $m[2],
            );
        }

        return null;
    }

    public function translateAe3HttpMessage(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return 'AE3 API вернул ответ уровня HTTP 5xx.';
        }

        if (preg_match('/^AE3 API returned HTTP (\d+) for ([A-Z]+) (.+)$/i', $normalized, $m) === 1) {
            return sprintf(
                'AE3 API вернул HTTP %d для %s %s.',
                (int) $m[1],
                strtoupper($m[2]),
                $m[3],
            );
        }

        return null;
    }
}
