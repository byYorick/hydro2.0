<?php

declare(strict_types=1);

namespace App\Services\AlertLocalization;

/**
 * Парсит structured английские сообщения AE3 / history-logger по regex-паттернам
 * и переводит их в русскую форму с подстановкой параметров.
 *
 * Паттерны сгруппированы: AE3 task lifecycle, correction, irrigation, history-logger, legacy commands.
 * Одна функция = один regex (flat list) — проще добавлять новые паттерны при необходимости.
 */
class AlertStructuredMessageParser
{
    public function parse(?string $message): ?string
    {
        $normalized = trim((string) $message);
        if ($normalized === '') {
            return null;
        }

        return $this->matchAe3Runtime($normalized)
            ?? $this->matchTaskLifecycle($normalized)
            ?? $this->matchCommandLifecycle($normalized)
            ?? $this->matchConfigValidation($normalized)
            ?? $this->matchHistoryLogger($normalized)
            ?? $this->matchSensors($normalized)
            ?? $this->matchMisc($normalized);
    }

    private function matchAe3Runtime(string $s): ?string
    {
        if (preg_match('/^Intent skipped: zone busy(?: \(zone_id=(\d+)\))?$/i', $s, $m) === 1) {
            $zoneId = isset($m[1]) && $m[1] !== '' ? (int) $m[1] : null;
            return $zoneId !== null
                ? sprintf('Повторный запуск отклонён: зона %d уже занята активной задачей или intent.', $zoneId)
                : 'Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.';
        }
        if (preg_match('/^Task execution exceeded (\d+)s timeout$/i', $s, $m) === 1) {
            return sprintf('Выполнение задачи превысило timeout %d с.', (int) $m[1]);
        }

        return null;
    }

    private function matchTaskLifecycle(string $s): ?string
    {
        if (preg_match('/^Task (\d+) has no claimed_by during startup recovery$/i', $s, $m) === 1) {
            return sprintf('Во время startup recovery у задачи %d отсутствует claimed_by.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) has no confirmed external command during startup recovery$/i', $s, $m) === 1) {
            return sprintf('Во время startup recovery у задачи %d не подтверждена внешняя команда.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) is waiting_command without resolvable legacy command$/i', $s, $m) === 1) {
            return sprintf('Задача %d находится в waiting_command без разрешимой legacy-команды.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) correction interrupted during ([a-z0-9_\-]+)$/i', $s, $m) === 1) {
            return sprintf('Коррекция задачи %d была прервана на шаге %s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^Task (\d+) has no claimed_by owner$/i', $s, $m) === 1) {
            return sprintf('У задачи %d отсутствует владелец claimed_by.', (int) $m[1]);
        }
        if (preg_match('/^Unable to mark task (\d+) running$/i', $s, $m) === 1) {
            return sprintf('Не удалось перевести задачу %d в состояние running.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) could not persist poll outcome$/i', $s, $m) === 1) {
            return sprintf('Не удалось сохранить результат poll для задачи %d.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) could not transition to completed$/i', $s, $m) === 1) {
            return sprintf('Не удалось перевести задачу %d в состояние completed.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) could not transition to ([a-z0-9_\-]+)$/i', $s, $m) === 1) {
            return sprintf('Не удалось перевести задачу %d на stage %s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^Task (\d+) could not persist correction state$/i', $s, $m) === 1) {
            return sprintf('Не удалось сохранить состояние коррекции для задачи %d.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) has no ae_command for recovery$/i', $s, $m) === 1) {
            return sprintf('У задачи %d отсутствует связанная ae_command для recovery.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) missing during ae_commands insert \(likely concurrent cleanup\)$/i', $s, $m) === 1) {
            return sprintf('Задача %d исчезла во время вставки в ae_commands, вероятно из-за конкурентного cleanup.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) missing after HL publish while linking ae_commands \(likely concurrent cleanup\); cmd_id=(.+)$/i', $s, $m) === 1) {
            return sprintf('Задача %d исчезла после публикации через history-logger при связывании ae_commands; cmd_id=%s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^Task (\d+) missing before waiting_command transition \(likely concurrent cleanup\); cmd_id=(.+)$/i', $s, $m) === 1) {
            return sprintf('Задача %d исчезла перед переходом в waiting_command; cmd_id=%s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^Task (\d+) missing during publish pipeline \(likely concurrent cleanup\): (.+)$/i', $s, $m) === 1) {
            return sprintf('Задача %d исчезла во время publish pipeline: %s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^Task (\d+) could not enter waiting_command$/i', $s, $m) === 1) {
            return sprintf('Не удалось перевести задачу %d в waiting_command.', (int) $m[1]);
        }
        if (preg_match('/^Task (\d+) could not fail on ([A-Z_]+)$/i', $s, $m) === 1) {
            return sprintf('Не удалось перевести задачу %d в failed после terminal status %s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^Task (\d+) became ([a-z_]+) during command roundtrip$/i', $s, $m) === 1) {
            return sprintf('Во время command roundtrip задача %d перешла в состояние %s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^Unable to create canonical task for zone_id=(\d+)$/i', $s, $m) === 1) {
            return sprintf('Не удалось создать canonical task для зоны %d.', (int) $m[1]);
        }
        if (preg_match('/^Unable to move task_id=(\d+) into waiting_command$/i', $s, $m) === 1) {
            return sprintf('Не удалось перевести task_id=%d в waiting_command.', (int) $m[1]);
        }
        if (preg_match('/^Unable to fail task_id=(\d+) after publish error$/i', $s, $m) === 1) {
            return sprintf('Не удалось перевести task_id=%d в failed после ошибки публикации.', (int) $m[1]);
        }
        if (preg_match('/^Unable to recover task_id=(\d+) into waiting_command$/i', $s, $m) === 1) {
            return sprintf('Не удалось восстановить task_id=%d в состояние waiting_command.', (int) $m[1]);
        }
        if (preg_match('/^Unsupported startup recovery outcome=(.+)$/i', $s, $m) === 1) {
            return sprintf('Неподдерживаемый результат startup recovery: %s.', $m[1]);
        }
        if (preg_match('/^Unsupported native recovery state=(.+)$/i', $s, $m) === 1) {
            return sprintf('Неподдерживаемое состояние native recovery: %s.', $m[1]);
        }

        return null;
    }

    private function matchCommandLifecycle(string $s): ?string
    {
        if (preg_match('/^Command polling exceeded stage deadline for task (\d+) stage=(.+)$/i', $s, $m) === 1) {
            return sprintf('Опрос команды превысил дедлайн stage для задачи %d на этапе %s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^Command terminal status ([A-Z_]+)$/i', $s, $m) === 1) {
            return sprintf('Команда завершилась terminal status %s.', $m[1]);
        }
        if (preg_match('/^Legacy commands\.id not found for zone_id=(\d+) cmd_id=(.+)$/i', $s, $m) === 1) {
            return sprintf('Не найдена запись legacy commands.id для зоны %d и cmd_id=%s.', (int) $m[1], $m[2]);
        }
        if (preg_match('/^ae_commands\.id=(\d+) not updated after publish \(task still present\)$/i', $s, $m) === 1) {
            return sprintf('После публикации не удалось обновить ae_commands.id=%d, хотя задача ещё существует.', (int) $m[1]);
        }
        if (preg_match('/^ae_command (.+) has neither external_id nor payload\.cmd_id$/i', $s, $m) === 1) {
            return sprintf('У ae_command %s отсутствуют и external_id, и payload.cmd_id.', $m[1]);
        }
        if (preg_match('/^Legacy command not found for external_id=(.+)$/i', $s, $m) === 1) {
            return sprintf('Не найдена legacy-команда для external_id=%s.', $m[1]);
        }
        if (preg_match('/^Unsupported legacy status=(.+)$/i', $s, $m) === 1) {
            return sprintf('Неподдерживаемый legacy-статус: %s.', $m[1]);
        }

        return null;
    }

    private function matchConfigValidation(string $s): ?string
    {
        if (preg_match('/^Unknown stage ([a-z0-9_\-]+) in topology ([a-z0-9_\-]+)$/i', $s, $m) === 1) {
            return sprintf('Неизвестный stage %s для topology %s.', $m[1], $m[2]);
        }
        if (preg_match('/^Unsupported task_type for CycleStartPlanner: (.+)$/i', $s, $m) === 1) {
            return sprintf('CycleStartPlanner не поддерживает task_type=%s.', $m[1]);
        }
        if (preg_match('/^AutomationTask\.zone_id=(\d+) does not match ZoneSnapshot\.zone_id=(\d+)$/i', $s, $m) === 1) {
            return sprintf('AutomationTask.zone_id=%d не совпадает с ZoneSnapshot.zone_id=%d.', (int) $m[1], (int) $m[2]);
        }
        if (preg_match('/^Unsupported command_plans\.schema_version=(.+)$/i', $s, $m) === 1) {
            return sprintf('Неподдерживаемая версия command_plans.schema_version=%s.', $m[1]);
        }
        if (preg_match('/^Unsupported diagnostics workflow for cycle_start planner: (.+)$/i', $s, $m) === 1) {
            return sprintf('CycleStartPlanner не поддерживает diagnostics workflow=%s.', $m[1]);
        }
        if (preg_match('/^Invalid command plan step at index=(\d+)$/i', $s, $m) === 1) {
            return sprintf('Некорректный шаг command plan на позиции %d.', (int) $m[1]);
        }
        if (preg_match('/^Each command step must define channel\/cmd\/params \(index=(\d+)\)$/i', $s, $m) === 1) {
            return sprintf('Каждый шаг command plan должен содержать channel/cmd/params (index=%d).', (int) $m[1]);
        }
        if (preg_match('/^Ambiguous system channel resolution for node_type=(.+)$/i', $s, $m) === 1) {
            return sprintf('Неоднозначное разрешение system channel для node_type=%s.', $m[1]);
        }
        if (preg_match('/^Expected exactly one runtime node for node_types=(.+)$/i', $s, $m) === 1) {
            return sprintf('Ожидалась ровно одна runtime-нода для node_types=%s.', $m[1]);
        }
        if (preg_match('/^Missing required correction_config field: (.+)$/i', $s, $m) === 1) {
            return sprintf('Отсутствует обязательное поле correction_config: %s.', $m[1]);
        }
        if (preg_match('/^Missing or invalid correction_config field: (.+)$/i', $s, $m) === 1) {
            return sprintf('Поле correction_config отсутствует или некорректно: %s.', $m[1]);
        }
        if (preg_match('/^correction_config field (.+) must be >= (.+), got (.+)$/i', $s, $m) === 1) {
            return sprintf('Поле correction_config %s должно быть >= %s, получено %s.', $m[1], $m[2], $m[3]);
        }
        if (preg_match('/^correction_config field (.+) must be <= (.+), got (.+)$/i', $s, $m) === 1) {
            return sprintf('Поле correction_config %s должно быть <= %s, получено %s.', $m[1], $m[2], $m[3]);
        }

        return null;
    }

    private function matchHistoryLogger(string $s): ?string
    {
        if (preg_match('/^Unable to resolve greenhouse_uid for zone_id=(\d+)$/i', $s, $m) === 1) {
            return sprintf('Не удалось определить greenhouse_uid для зоны %d.', (int) $m[1]);
        }
        if (preg_match('/^history-logger request failed: (.+)$/i', $s, $m) === 1) {
            return sprintf('Запрос к history-logger завершился ошибкой: %s.', $m[1]);
        }
        if (preg_match('/^history-logger publish failed with HTTP (\d+)$/i', $s, $m) === 1) {
            return sprintf('history-logger не смог опубликовать команду и вернул HTTP %d.', (int) $m[1]);
        }

        return null;
    }

    private function matchSensors(string $s): ?string
    {
        if (preg_match('/^Level sensor unavailable: (.+)$/i', $s, $m) === 1) {
            return sprintf('Недоступен датчик уровня: %s.', $m[1]);
        }
        if (preg_match('/^Level sensor stale: (.+)$/i', $s, $m) === 1) {
            return sprintf('Данные датчика уровня устарели: %s.', $m[1]);
        }
        if (preg_match('/^(PH|EC) telemetry unavailable for target evaluation$/i', $s, $m) === 1) {
            return sprintf('Телеметрия %s недоступна для оценки достижения target.', strtoupper($m[1]));
        }
        if (preg_match('/^(PH|EC) telemetry stale for target evaluation$/i', $s, $m) === 1) {
            return sprintf('Телеметрия %s устарела для оценки достижения target.', strtoupper($m[1]));
        }
        if (preg_match('/^Tank sensors inconsistent: max=1 min=0 \((.+)\)$/i', $s, $m) === 1) {
            return sprintf('Датчики бака противоречат друг другу: max=1 и min=0 (%s).', $m[1]);
        }

        return null;
    }

    private function matchMisc(string $s): ?string
    {
        if (preg_match('/^No handler for key=(.+) \(stage=(.+)\)$/i', $s, $m) === 1) {
            return sprintf('Для stage %s не найден handler %s.', $m[2], $m[1]);
        }
        if (preg_match('/^Unknown StageOutcome\.kind=(.+)$/i', $s, $m) === 1) {
            return sprintf('Неизвестный тип результата StageOutcome: %s.', $m[1]);
        }

        return null;
    }
}
