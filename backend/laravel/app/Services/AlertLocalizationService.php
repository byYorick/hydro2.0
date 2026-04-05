<?php

namespace App\Services;

class AlertLocalizationService
{
    public function __construct(
        private AlertCatalogService $alertCatalogService,
    ) {}

    /**
     * @param array<string, mixed>|null $details
     * @return array{code:string,title:string,description:string,recommendation:string,message:string}
     */
    public function present(?string $code, ?string $type = null, ?array $details = null, ?string $source = null): array
    {
        $payload = is_array($details) ? $details : [];
        $resolvedCode = $this->alertCatalogService->normalizeCode($code ?? $payload['code'] ?? null);
        $catalog = $this->alertCatalogService->resolve($resolvedCode, $source ?? ($payload['source'] ?? null), $payload);

        $title = $this->resolveTitle($resolvedCode, $catalog, $type, $payload);
        $description = $this->resolveDescription($catalog, $payload);
        $recommendation = $this->resolveRecommendation($catalog, $payload);
        $message = $this->resolveMessage(
            code: $resolvedCode,
            type: $type,
            details: $payload,
            description: $description,
        );

        return [
            'code' => $resolvedCode !== '' ? $resolvedCode : 'unknown_alert',
            'title' => $title,
            'description' => $description,
            'recommendation' => $recommendation,
            'message' => $message,
        ];
    }

    /**
     * @param array<string, mixed> $catalog
     * @param array<string, mixed> $details
     */
    private function resolveTitle(string $code, array $catalog, ?string $type, array $details): string
    {
        $title = $this->stringValue($details, ['title']);
        if ($title !== null) {
            return $title;
        }

        $translatedType = $this->translateType($type);
        if (($code === '' || $code === 'unknown_alert') && $translatedType !== null) {
            return $translatedType;
        }

        $catalogTitle = trim((string) ($catalog['title'] ?? ''));
        if ($catalogTitle !== '') {
            return $catalogTitle;
        }

        if ($translatedType !== null) {
            return $translatedType;
        }

        return 'Системное предупреждение';
    }

    /**
     * @param array<string, mixed> $catalog
     * @param array<string, mixed> $details
     */
    private function resolveDescription(array $catalog, array $details): string
    {
        $description = $this->stringValue($details, ['description']);
        if ($description !== null && $this->looksLocalized($description)) {
            return $description;
        }

        $catalogDescription = trim((string) ($catalog['description'] ?? ''));
        if ($catalogDescription !== '') {
            return $catalogDescription;
        }

        return 'Событие требует проверки по журналам сервиса.';
    }

    /**
     * @param array<string, mixed> $catalog
     * @param array<string, mixed> $details
     */
    private function resolveRecommendation(array $catalog, array $details): string
    {
        $recommendation = $this->stringValue($details, ['recommendation']);
        if ($recommendation !== null && $this->looksLocalized($recommendation)) {
            return $recommendation;
        }

        $catalogRecommendation = trim((string) ($catalog['recommendation'] ?? ''));
        if ($catalogRecommendation !== '') {
            return $catalogRecommendation;
        }

        return 'Проверьте детали алерта и состояние сервисов.';
    }

    /**
     * @param array<string, mixed> $details
     */
    private function resolveMessage(string $code, ?string $type, array $details, string $description): string
    {
        $rawMessage = $this->stringValue($details, ['message', 'msg', 'reason', 'error_message']);

        if ($code === 'biz_ae3_task_failed') {
            $translatedTaskFailure = $this->translateByCode($code, $rawMessage, $details);
            if ($translatedTaskFailure !== null) {
                return $translatedTaskFailure;
            }
        }

        if ($rawMessage !== null && $this->looksLocalized($rawMessage)) {
            return $rawMessage;
        }

        $translatedByCode = $this->translateByCode($code, $rawMessage, $details);
        if ($translatedByCode !== null) {
            return $translatedByCode;
        }

        if ($rawMessage !== null) {
            $translatedRaw = $this->translateRawMessage($rawMessage);
            if ($translatedRaw !== null) {
                return $translatedRaw;
            }
        }

        $translatedType = $this->translateType($type);
        if ($translatedType !== null && $translatedType !== 'Системное предупреждение') {
            return $translatedType;
        }

        return $description;
    }

    /**
     * @param array<string, mixed> $details
     */
    private function translateByCode(string $code, ?string $rawMessage, array $details): ?string
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

    /**
     * @param array<string, mixed> $details
     */
    private function translateAe3TaskFailed(?string $message, array $details): string
    {
        $taskId = $this->scalarValue($details, ['task_id']);
        $taskType = $this->stringValue($details, ['task_type']);
        $stage = $this->stringValue($details, ['stage']);
        $workflowPhase = $this->stringValue($details, ['workflow_phase']);
        $topology = $this->stringValue($details, ['topology']);
        $corrStep = $this->stringValue($details, ['corr_step']);
        $retryCount = $this->integerValue($details, ['stage_retry_count']);

        $reasonCode = $this->alertCatalogService->normalizeCode($details['error_code'] ?? null);
        $reasonRaw = $this->stringValue($details, ['error_message', 'message', 'reason', 'msg']) ?? $message;
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

        $messageParts = ['Задача AE3'];
        if ($taskId !== null) {
            $messageParts[] = '#'.$taskId;
        }

        $headline = implode(' ', $messageParts);
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
        if ($context !== []) {
            $summary .= ': '.implode(', ', $context).'.';
        } else {
            $summary .= '.';
        }

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

        $probeName = $this->stringValue($timeoutDetails, ['probe_name']);
        $cmdId = $this->stringValue($timeoutDetails, ['cmd_id']);
        $nodeUid = $this->stringValue($timeoutDetails, ['node_uid']);
        $channel = $this->stringValue($timeoutDetails, ['channel']);
        $nodeStatus = $this->stringValue($timeoutDetails, ['node_status']);
        $lastSeenAgeSec = $this->integerValue($timeoutDetails, ['node_last_seen_age_sec']);
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

        $message = $parts !== []
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
            $message .= ' Контекст: '.implode(', ', $context).'.';
        }

        return $message;
    }

    private function translateRawMessage(string $message): ?string
    {
        $normalized = trim($message);
        if ($normalized === '') {
            return null;
        }

        $exactMap = [
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
        ];

        if (array_key_exists($normalized, $exactMap)) {
            return $exactMap[$normalized];
        }

        return $this->translateCorrectionNoEffect($normalized, [])
            ?? $this->translateIrrStateMismatch($normalized)
            ?? $this->translateAe3StructuredMessage($normalized)
            ?? $this->translateAe3HttpMessage($normalized);
    }

    private function translateIrrStateMismatch(?string $message): ?string
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

    private function translateAe3StructuredMessage(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return null;
        }

        if (preg_match('/^Intent skipped: zone busy(?: \(zone_id=(\d+)\))?$/i', $normalized, $matches) === 1) {
            $zoneId = isset($matches[1]) && $matches[1] !== '' ? (int) $matches[1] : null;
            return $zoneId !== null
                ? sprintf('Повторный запуск отклонён: зона %d уже занята активной задачей или intent.', $zoneId)
                : 'Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.';
        }

        if (preg_match('/^Task execution exceeded (\d+)s timeout$/i', $normalized, $matches) === 1) {
            return sprintf('Выполнение задачи превысило timeout %d с.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) has no claimed_by during startup recovery$/i', $normalized, $matches) === 1) {
            return sprintf('Во время startup recovery у задачи %d отсутствует claimed_by.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) has no confirmed external command during startup recovery$/i', $normalized, $matches) === 1) {
            return sprintf('Во время startup recovery у задачи %d не подтверждена внешняя команда.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) is waiting_command without resolvable legacy command$/i', $normalized, $matches) === 1) {
            return sprintf('Задача %d находится в waiting_command без разрешимой legacy-команды.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) correction interrupted during ([a-z0-9_\-]+)$/i', $normalized, $matches) === 1) {
            return sprintf(
                'Коррекция задачи %d была прервана на шаге %s.',
                (int) $matches[1],
                $matches[2],
            );
        }

        if (preg_match('/^Unknown stage ([a-z0-9_\-]+) in topology ([a-z0-9_\-]+)$/i', $normalized, $matches) === 1) {
            return sprintf('Неизвестный stage %s для topology %s.', $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) has no claimed_by owner$/i', $normalized, $matches) === 1) {
            return sprintf('У задачи %d отсутствует владелец claimed_by.', (int) $matches[1]);
        }

        if (preg_match('/^Unable to mark task (\d+) running$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d в состояние running.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) could not persist poll outcome$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось сохранить результат poll для задачи %d.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) could not transition to completed$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d в состояние completed.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) could not transition to ([a-z0-9_\-]+)$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d на stage %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) could not persist correction state$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось сохранить состояние коррекции для задачи %d.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) has no ae_command for recovery$/i', $normalized, $matches) === 1) {
            return sprintf('У задачи %d отсутствует связанная ae_command для recovery.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) missing during ae_commands insert \(likely concurrent cleanup\)$/i', $normalized, $matches) === 1) {
            return sprintf('Задача %d исчезла во время вставки в ae_commands, вероятно из-за конкурентного cleanup.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) missing after HL publish while linking ae_commands \(likely concurrent cleanup\); cmd_id=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Задача %d исчезла после публикации через history-logger при связывании ae_commands; cmd_id=%s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) missing before waiting_command transition \(likely concurrent cleanup\); cmd_id=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Задача %d исчезла перед переходом в waiting_command; cmd_id=%s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) missing during publish pipeline \(likely concurrent cleanup\): (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Задача %d исчезла во время publish pipeline: %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) could not enter waiting_command$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d в waiting_command.', (int) $matches[1]);
        }

        if (preg_match('/^Task (\d+) could not fail on ([A-Z_]+)$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось перевести задачу %d в failed после terminal status %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Task (\d+) became ([a-z_]+) during command roundtrip$/i', $normalized, $matches) === 1) {
            return sprintf('Во время command roundtrip задача %d перешла в состояние %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Command polling exceeded stage deadline for task (\d+) stage=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Опрос команды превысил дедлайн stage для задачи %d на этапе %s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^Command terminal status ([A-Z_]+)$/i', $normalized, $matches) === 1) {
            return sprintf('Команда завершилась terminal status %s.', $matches[1]);
        }

        if (preg_match('/^Legacy commands\.id not found for zone_id=(\d+) cmd_id=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Не найдена запись legacy commands.id для зоны %d и cmd_id=%s.', (int) $matches[1], $matches[2]);
        }

        if (preg_match('/^ae_commands\.id=(\d+) not updated after publish \(task still present\)$/i', $normalized, $matches) === 1) {
            return sprintf('После публикации не удалось обновить ae_commands.id=%d, хотя задача ещё существует.', (int) $matches[1]);
        }

        if (preg_match('/^ae_command (.+) has neither external_id nor payload\.cmd_id$/i', $normalized, $matches) === 1) {
            return sprintf('У ae_command %s отсутствуют и external_id, и payload.cmd_id.', $matches[1]);
        }

        if (preg_match('/^Unable to create canonical task for zone_id=(\d+)$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось создать canonical task для зоны %d.', (int) $matches[1]);
        }

        if (preg_match('/^Unable to move task_id=(\d+) into waiting_command$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось перевести task_id=%d в waiting_command.', (int) $matches[1]);
        }

        if (preg_match('/^Unable to fail task_id=(\d+) after publish error$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось перевести task_id=%d в failed после ошибки публикации.', (int) $matches[1]);
        }

        if (preg_match('/^Unable to recover task_id=(\d+) into waiting_command$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось восстановить task_id=%d в состояние waiting_command.', (int) $matches[1]);
        }

        if (preg_match('/^Unsupported startup recovery outcome=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Неподдерживаемый результат startup recovery: %s.', $matches[1]);
        }

        if (preg_match('/^Unsupported native recovery state=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Неподдерживаемое состояние native recovery: %s.', $matches[1]);
        }

        if (preg_match('/^Unsupported task_type for CycleStartPlanner: (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('CycleStartPlanner не поддерживает task_type=%s.', $matches[1]);
        }

        if (preg_match('/^AutomationTask\.zone_id=(\d+) does not match ZoneSnapshot\.zone_id=(\d+)$/i', $normalized, $matches) === 1) {
            return sprintf('AutomationTask.zone_id=%d не совпадает с ZoneSnapshot.zone_id=%d.', (int) $matches[1], (int) $matches[2]);
        }

        if (preg_match('/^Unsupported command_plans\.schema_version=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Неподдерживаемая версия command_plans.schema_version=%s.', $matches[1]);
        }

        if (preg_match('/^Unsupported diagnostics workflow for cycle_start planner: (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('CycleStartPlanner не поддерживает diagnostics workflow=%s.', $matches[1]);
        }

        if (preg_match('/^Invalid command plan step at index=(\d+)$/i', $normalized, $matches) === 1) {
            return sprintf('Некорректный шаг command plan на позиции %d.', (int) $matches[1]);
        }

        if (preg_match('/^Each command step must define channel\/cmd\/params \(index=(\d+)\)$/i', $normalized, $matches) === 1) {
            return sprintf('Каждый шаг command plan должен содержать channel/cmd/params (index=%d).', (int) $matches[1]);
        }

        if (preg_match('/^Ambiguous system channel resolution for node_type=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Неоднозначное разрешение system channel для node_type=%s.', $matches[1]);
        }

        if (preg_match('/^Expected exactly one runtime node for node_types=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Ожидалась ровно одна runtime-нода для node_types=%s.', $matches[1]);
        }

        if (preg_match('/^Missing required correction_config field: (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Отсутствует обязательное поле correction_config: %s.', $matches[1]);
        }

        if (preg_match('/^Missing or invalid correction_config field: (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Поле correction_config отсутствует или некорректно: %s.', $matches[1]);
        }

        if (preg_match('/^correction_config field (.+) must be >= (.+), got (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Поле correction_config %s должно быть >= %s, получено %s.', $matches[1], $matches[2], $matches[3]);
        }

        if (preg_match('/^correction_config field (.+) must be <= (.+), got (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Поле correction_config %s должно быть <= %s, получено %s.', $matches[1], $matches[2], $matches[3]);
        }

        if (preg_match('/^Unable to resolve greenhouse_uid for zone_id=(\d+)$/i', $normalized, $matches) === 1) {
            return sprintf('Не удалось определить greenhouse_uid для зоны %d.', (int) $matches[1]);
        }

        if (preg_match('/^history-logger request failed: (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Запрос к history-logger завершился ошибкой: %s.', $matches[1]);
        }

        if (preg_match('/^history-logger publish failed with HTTP (\d+)$/i', $normalized, $matches) === 1) {
            return sprintf('history-logger не смог опубликовать команду и вернул HTTP %d.', (int) $matches[1]);
        }

        if (preg_match('/^Legacy command not found for external_id=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Не найдена legacy-команда для external_id=%s.', $matches[1]);
        }

        if (preg_match('/^Unsupported legacy status=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Неподдерживаемый legacy-статус: %s.', $matches[1]);
        }

        if (preg_match('/^Level sensor unavailable: (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Недоступен датчик уровня: %s.', $matches[1]);
        }

        if (preg_match('/^Level sensor stale: (.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Данные датчика уровня устарели: %s.', $matches[1]);
        }

        if (preg_match('/^(PH|EC) telemetry unavailable for target evaluation$/i', $normalized, $matches) === 1) {
            return sprintf('Телеметрия %s недоступна для оценки достижения target.', strtoupper($matches[1]));
        }

        if (preg_match('/^(PH|EC) telemetry stale for target evaluation$/i', $normalized, $matches) === 1) {
            return sprintf('Телеметрия %s устарела для оценки достижения target.', strtoupper($matches[1]));
        }

        if (preg_match('/^Tank sensors inconsistent: max=1 min=0 \((.+)\)$/i', $normalized, $matches) === 1) {
            return sprintf('Датчики бака противоречат друг другу: max=1 и min=0 (%s).', $matches[1]);
        }

        if (preg_match('/^No handler for key=(.+) \(stage=(.+)\)$/i', $normalized, $matches) === 1) {
            return sprintf('Для stage %s не найден handler %s.', $matches[2], $matches[1]);
        }

        if (preg_match('/^Unknown StageOutcome\.kind=(.+)$/i', $normalized, $matches) === 1) {
            return sprintf('Неизвестный тип результата StageOutcome: %s.', $matches[1]);
        }

        return null;
    }

    private function translateCorrectionConfigMissing(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return 'В конфигурации коррекции отсутствуют обязательные поля; критические параметры коррекции переведены в fail-closed режим.';
        }

        if (preg_match('/^Zone (\d+) correction_config\.([a-z0-9_\-]+) missing required fields: (.+); fail-closed for critical correction parameters$/i', $normalized, $matches) === 1) {
            return sprintf(
                'В зоне %d в correction_config.%s отсутствуют обязательные поля: %s; критические параметры коррекции переведены в fail-closed режим.',
                (int) $matches[1],
                $matches[2],
                $matches[3],
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

        if (preg_match('/^Zone (\d+) missing required pid authority documents for pid_type=(.+); fail-closed for critical correction parameters$/i', $normalized, $matches) === 1) {
            return sprintf(
                'В зоне %d отсутствуют обязательные PID authority-документы для pid_type=%s; критические параметры коррекции переведены в fail-closed режим.',
                (int) $matches[1],
                $matches[2],
            );
        }

        if (preg_match('/^Zone (\d+) has no pid authority mapping; fail-closed for critical correction parameters$/i', $normalized, $matches) === 1) {
            return sprintf(
                'В зоне %d отсутствует mapping PID authority-конфига; критические параметры коррекции переведены в fail-closed режим.',
                (int) $matches[1],
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

        if (preg_match('/^Zone (\d+) current recipe phase has no target_(ph|ec); automation requires recipe-phase pH\/EC targets and forbids defaults or runtime overrides$/i', $normalized, $matches) === 1) {
            return sprintf(
                'В зоне %d в актуальной фазе рецепта отсутствует target_%s; automation переведена в fail-closed режим без defaults и runtime override.',
                (int) $matches[1],
                strtolower($matches[2]),
            );
        }

        if (preg_match('/^Zone (\d+) current recipe phase target_(ph|ec) is not numeric: (.+)$/i', $normalized, $matches) === 1) {
            return sprintf(
                'В зоне %d в актуальной фазе рецепта target_%s имеет нечисловое значение: %s.',
                (int) $matches[1],
                strtolower($matches[2]),
                $matches[3],
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

        if (preg_match('/^(EC|PH) dosing pump calibration is required \(channel=([^,]+), node=([^)]+)\)$/i', $normalized, $matches) === 1) {
            return sprintf(
                'Для %s требуется калибровка дозирующего насоса (channel=%s, node=%s).',
                strtoupper($matches[1]),
                $matches[2],
                $matches[3],
            );
        }

        return null;
    }

    /**
     * @param array<string, mixed> $details
     */
    private function translateCorrectionNoEffect(?string $message, array $details): ?string
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

        if (preg_match('/^(PH|EC) correction produced no observable response (\d+) times in a row\.$/i', $normalized, $matches) === 1) {
            return sprintf(
                'Коррекция %s не дала наблюдаемого отклика %d раз подряд.',
                strtoupper($matches[1]),
                (int) $matches[2],
            );
        }

        return null;
    }

    private function translateAe3HttpMessage(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return 'AE3 API вернул ответ уровня HTTP 5xx.';
        }

        if (preg_match('/^AE3 API returned HTTP (\d+) for ([A-Z]+) (.+)$/i', $normalized, $matches) === 1) {
            return sprintf(
                'AE3 API вернул HTTP %d для %s %s.',
                (int) $matches[1],
                strtoupper($matches[2]),
                $matches[3],
            );
        }

        return null;
    }

    private function translateType(?string $type): ?string
    {
        $normalized = strtolower(trim((string) $type));
        if ($normalized === '') {
            return null;
        }

        return match ($normalized) {
            'ae3 correction exhausted' => 'Исчерпаны попытки коррекции AE3',
            'ae3 correction no effect' => 'Коррекция AE3 не даёт эффекта',
            'ae3 clean fill timeout' => 'Таймаут наполнения чистой водой',
            'ae3 solution fill timeout' => 'Таймаут наполнения раствором',
            'ae3 zone lease lost' => 'Потерян lease зоны AE3',
            'ae3 zone lease release failed' => 'Не удалось освободить lease зоны AE3',
            'ae3 background task crashed' => 'Сбой фоновой задачи AE3',
            'ae3 api unhandled exception' => 'Необработанное исключение AE3 API',
            'ae3 api http 5xx' => 'Ошибка AE3 API уровня HTTP 5xx',
            'ae3 irrigation decision skip' => 'Decision-controller полива пропустил запуск',
            'ae3 irrigation decision degraded' => 'Decision-controller полива разрешил деградированный запуск',
            'ae3 irrigation decision fail' => 'Decision-controller полива отклонил запуск',
            'ae3 irrigation solution min' => 'Сработал нижний уровень раствора во время полива',
            'ae3 irrigation replay exhausted' => 'Исчерпан бюджет повторов полива',
            'ae3 irrigation wait ready timeout' => 'Таймаут ожидания READY перед поливом',
            'ae3 irrigation correction exhausted' => 'Исчерпаны попытки коррекции во время полива',
            'command ack not found' => 'ACK для неизвестной команды',
            'command send failed' => 'Команда не отправлена',
            'command node/zone mismatch' => 'Несоответствие node/zone для команды',
            'fill mode failed' => 'Ошибка режима Fill',
            'drain mode failed' => 'Ошибка режима Drain',
            'flow calibration failed' => 'Ошибка калибровки расхода',
            'pump calibration failed' => 'Ошибка калибровки насоса',
            'telemetry anomaly' => 'Аномалия телеметрии',
            'digital twin live completion failed' => 'Ошибка live completion в Digital Twin',
            'digital twin simulation failed' => 'Ошибка симуляции Digital Twin',
            'live simulation start failed' => 'Не удалось запустить live simulation',
            'live simulation stop failed' => 'Не удалось остановить live simulation',
            'digital twin calibration failed' => 'Ошибка калибровки Digital Twin',
            'automation_engine' => 'Ошибка automation-engine',
            'nodeoffline' => 'Узел офлайн',
            'servicedown' => 'Сервис недоступен',
            'mqttbrokerdown' => 'MQTT брокер недоступен',
            'zonecriticalalert' => 'В зоне серия критических алертов',
            'highcommandfailurerate' => 'Высокий процент ошибок команд',
            'historyloggerqueueoverflow' => 'Очередь History Logger переполнена',
            'historyloggerqueuestale' => 'В очереди History Logger устаревшие элементы',
            'historyloggerdroppingmessages' => 'History Logger теряет сообщения',
            'historyloggerdatabaseerrors' => 'Ошибки базы данных в History Logger',
            'historyloggerslowprocessing' => 'History Logger обрабатывает сообщения слишком медленно',
            'historyloggernoprocessing' => 'History Logger не обрабатывает телеметрию',
            'historyloggerunknownnodeeventsspike' => 'Всплеск неизвестных событий нод в History Logger',
            'automationenginelooperrors' => 'Ошибки основного цикла Automation Engine',
            'automationengineconfigfetcherrors' => 'Automation Engine не может получить конфигурацию',
            'automationenginemqttpublisherrors' => 'Automation Engine не может публиковать команды',
            'automationengineslowzoneprocessing' => 'Automation Engine медленно обрабатывает зоны',
            'automationenginenozonechecks' => 'Automation Engine не проверяет зоны',
            'automationenginehigherrorrate' => 'Высокий общий уровень ошибок Automation Engine',
            'schedulertaskacceptlatencyhigh' => 'Высокая задержка принятия задач планировщика',
            'schedulertaskcompletionlatencyhigh' => 'Высокая задержка завершения задач планировщика',
            'schedulertaskfailureratehigh' => 'Высокий процент ошибок задач планировщика',
            'scheduleractivetasksbackloghigh' => 'Слишком большой backlog активных задач планировщика',
            'schedulertaskaccepttoterminallatencyslodegraded' => 'Деградация SLO по времени жизни задач планировщика',
            'schedulertaskdeadlineviolationratehigh' => 'Высокая доля нарушений дедлайна задач планировщика',
            'automationcommandeffectconfirmratelow' => 'Низкая доля подтверждённого эффекта команд',
            'automationtaskrecoverysuccessratelow' => 'Низкая успешность восстановления задач',
            'ae3zoneleaselost' => 'Потерян lease зоны AE3',
            'ae3zoneleasereleasefailed' => 'Не удалось освободить lease зоны AE3',
            'ae3stucktask' => 'Зависшая задача AE3',
            'ae3correctionexhausted' => 'AE3 исчерпал все попытки коррекции',
            'ae3stagedeadlineexceeded' => 'Этап AE3 превысил дедлайн',
            'ae3tickerrors' => 'Ошибки тиков worker AE3',
            default => null,
        };
    }

    /**
     * @param array<string, mixed> $details
     * @param string[] $keys
     */
    private function stringValue(array $details, array $keys): ?string
    {
        foreach ($keys as $key) {
            $value = $details[$key] ?? null;
            if (! is_string($value)) {
                continue;
            }

            $normalized = trim($value);
            if ($normalized !== '') {
                return $normalized;
            }
        }

        return null;
    }

    /**
     * @param array<string, mixed> $details
     * @param string[] $keys
     */
    private function scalarValue(array $details, array $keys): ?string
    {
        foreach ($keys as $key) {
            if (! array_key_exists($key, $details)) {
                continue;
            }

            $value = $details[$key];
            if (! is_scalar($value)) {
                continue;
            }

            $normalized = trim((string) $value);
            if ($normalized !== '') {
                return $normalized;
            }
        }

        return null;
    }

    /**
     * @param array<string, mixed> $details
     * @param string[] $keys
     */
    private function integerValue(array $details, array $keys): ?int
    {
        foreach ($keys as $key) {
            if (! array_key_exists($key, $details)) {
                continue;
            }

            $value = $details[$key];
            if (is_int($value)) {
                return $value;
            }

            if (is_string($value) && preg_match('/^-?\d+$/', trim($value)) === 1) {
                return (int) trim($value);
            }
        }

        return null;
    }

    private function looksLocalized(string $value): bool
    {
        return preg_match('/\p{Cyrillic}/u', $value) === 1;
    }
}
