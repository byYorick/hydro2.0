<?php

declare(strict_types=1);

namespace App\Services\AlertLocalization;

/**
 * Переводит raw-type alert'а (Prometheus / AE3 type-string) в русский заголовок.
 */
class AlertTypeTranslator
{
    private const TRANSLATIONS = [
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
    ];

    public function translate(?string $type): ?string
    {
        $normalized = strtolower(trim((string) $type));
        if ($normalized === '') {
            return null;
        }

        return self::TRANSLATIONS[$normalized] ?? null;
    }
}
