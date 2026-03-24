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
            'biz_correction_exhausted' => 'Цикл коррекции исчерпал все настроенные попытки.',
            'biz_clean_fill_timeout' => 'Превышено время ожидания заполнения бака чистой водой после всех циклов повтора.',
            'biz_solution_fill_timeout' => 'Превышено время ожидания заполнения бака раствором до завершения этапа.',
            'ae3_zone_lease_release_failed' => 'Не удалось освободить lease зоны после завершения задачи.',
            'ae3_zone_lease_lost' => 'Worker потерял lease зоны и продолжил выполнение без действительной блокировки.',
            'ae3_background_task_crashed' => 'Фоновая задача AE3 завершилась с аварией.',
            'ae3_api_unhandled_exception' => 'AE3 API завершился необработанным исключением.',
            'infra_command_ack_command_not_found' => $rawMessage ?? 'Laravel не нашёл команду при обработке ACK.',
            'biz_zone_correction_config_missing', 'zone_correction_config_missing_critical' => $this->translateCorrectionConfigMissing($rawMessage),
            'biz_zone_pid_config_missing', 'zone_pid_config_missing_critical' => $this->translatePidConfigMissing($rawMessage),
            'biz_zone_dosing_calibration_missing', 'zone_dosing_calibration_missing_critical' => $this->translateDosingCalibrationMissing($rawMessage),
            'biz_ph_correction_no_effect', 'biz_ec_correction_no_effect' => $this->translateCorrectionNoEffect($rawMessage, $details),
            'ae3_api_http_5xx' => $this->translateAe3HttpMessage($rawMessage),
            default => null,
        };
    }

    private function translateRawMessage(string $message): ?string
    {
        $normalized = trim($message);
        if ($normalized === '') {
            return null;
        }

        $exactMap = [
            'Correction cycle exhausted all configured attempts.' => 'Цикл коррекции исчерпал все настроенные попытки.',
            'Clean tank fill deadline exceeded after all retry cycles.' => 'Превышено время ожидания заполнения бака чистой водой после всех циклов повтора.',
            'Solution tank fill deadline exceeded before the stage could complete.' => 'Превышено время ожидания заполнения бака раствором до завершения этапа.',
            'Zone lease could not be released after task completion.' => 'Не удалось освободить lease зоны после завершения задачи.',
            'Zone lease could not be released after task completion — zone may be locked.' => 'Не удалось освободить lease зоны после завершения задачи: зона могла остаться заблокированной.',
            'Zone lease heartbeat failed and the worker kept running without a valid lease.' => 'Потерян heartbeat lease зоны, и worker продолжил выполнение без действительной блокировки.',
            'Zone lease heartbeat failed to extend — zone may be hijacked or frozen.' => 'Не удалось продлить heartbeat lease зоны: зону могли перехватить или она зависла.',
            'Task execution exceeded runtime timeout' => 'Выполнение задачи превысило допустимый runtime timeout.',
        ];

        if (array_key_exists($normalized, $exactMap)) {
            return $exactMap[$normalized];
        }

        return $this->translateCorrectionNoEffect($normalized, [])
            ?? $this->translateAe3HttpMessage($normalized);
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

    private function looksLocalized(string $value): bool
    {
        return preg_match('/\p{Cyrillic}/u', $value) === 1;
    }
}
