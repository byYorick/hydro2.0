<?php

namespace App\Support\Automation;

use InvalidArgumentException;

class ObservabilityThresholdsCatalog
{
    public const NAMESPACE_KEY = 'observability_thresholds';

    /**
     * @return array<string, int>
     */
    public static function defaults(): array
    {
        $values = [
            'waiting_command_warn_sec' => 120,
            'waiting_command_critical_sec' => 300,
            'task_dispatch_warn_sec' => 180,
            'task_dispatch_critical_sec' => 600,
            'workflow_snapshot_stale_warn_sec' => 120,
            'workflow_snapshot_stale_critical_sec' => 600,
            'correction_substep_warn_sec' => 180,
            'correction_substep_critical_sec' => 600,
            'nodes_stale_online_sec' => 120,
            'nodes_persistent_offline_sec' => 600,
            'level_clean_max_unlatched_sec' => 120,
            'level_solution_max_unlatched_sec' => 180,
            'level_solution_min_unlatched_sec' => 120,
            'scheduler_intent_pending_warn_sec' => 300,
            'scheduler_intent_pending_critical_sec' => 900,
            'scheduler_intent_claimed_warn_sec' => 180,
            'scheduler_intent_claimed_critical_sec' => 600,
            'scheduler_intent_running_warn_sec' => 600,
            'scheduler_intent_task_drift_warn_sec' => 45,
        ];

        foreach (self::stageKeys() as $stage => $label) {
            [$warn, $critical] = self::defaultStagePair($stage);
            $values["stage_{$stage}_warn_sec"] = $warn;
            $values["stage_{$stage}_critical_sec"] = $critical;
        }

        return $values;
    }

    /**
     * @return list<array{key:string,label:string,description:string,fields:list<array<string,mixed>>}>
     */
    public static function fieldCatalog(): array
    {
        $sec = static fn (string $path, string $label, string $description, int $min = 30, int $max = 86400): array => [
            'path' => $path,
            'label' => $label,
            'description' => $description,
            'type' => 'integer',
            'min' => $min,
            'max' => $max,
            'unit' => 'сек',
        ];

        $stageFields = [];
        foreach (self::stageKeys() as $stage => $stageLabel) {
            [$warnDefault, $criticalDefault] = self::defaultStagePair($stage);
            $stageFields[] = $sec(
                "stage_{$stage}_warn_sec",
                "{$stageLabel} — предупреждение",
                "Предупредить, если этап «{$stageLabel}» идёт дольше указанного времени (по умолчанию {$warnDefault} с). Этап при этом не прерывается — hint `stage_elapsed_long`.",
            );
            $stageFields[] = $sec(
                "stage_{$stage}_critical_sec",
                "{$stageLabel} — критично",
                "Повысить важность предупреждения, если этап «{$stageLabel}» идёт дольше указанного времени (по умолчанию {$criticalDefault} с).",
            );
        }

        return FieldCatalogHelpBuilder::attachHelp([
            [
                'key' => 'observability_commands',
                'label' => 'Ответы узлов на команды',
                'description' => 'Через сколько считать, что узел не ответил на команду, а задача так и не началась.',
                'fields' => [
                    $sec('waiting_command_warn_sec', 'Узел не отвечает — предупреждение', 'Задача ждёт ответа узла на отправленную команду дольше указанного времени. Отсчёт идёт от последнего изменения задачи (hint `waiting_command_stuck`).'),
                    $sec('waiting_command_critical_sec', 'Узел не отвечает — критично', 'Порог, после которого ожидание ответа считается критичным. Должен быть больше порога предупреждения.'),
                    $sec('task_dispatch_warn_sec', 'Задача не стартует — предупреждение', 'Задача принята, но так и не перешла в выполнение дольше указанного времени (hint `task_dispatch_stuck`).'),
                    $sec('task_dispatch_critical_sec', 'Задача не стартует — критично', 'Порог, после которого задержка запуска задачи считается критичной.'),
                ],
            ],
            [
                'key' => 'observability_runtime_diagnostics',
                'label' => 'Состояние зоны и коррекция',
                'description' => 'Через сколько считать, что состояние зоны перестало обновляться, а коррекция pH/EC зависла.',
                'fields' => [
                    $sec('workflow_snapshot_stale_warn_sec', 'Состояние зоны не обновляется — предупреждение', 'Зона выполняет этап, но её состояние не обновлялось дольше указанного времени (hint `workflow_snapshot_stale`).'),
                    $sec('workflow_snapshot_stale_critical_sec', 'Состояние зоны не обновляется — критично', 'Порог, после которого устаревшее состояние зоны считается критичным.'),
                    $sec('correction_substep_warn_sec', 'Шаг коррекции завис — предупреждение', 'Ожидание внутри цикла коррекции pH/EC длится дольше указанного времени (hint `correction_substep_stalled`).'),
                    $sec('correction_substep_critical_sec', 'Шаг коррекции завис — критично', 'Порог, после которого зависший шаг коррекции считается критичным.'),
                ],
            ],
            [
                'key' => 'observability_nodes',
                'label' => 'Связь с узлами зоны',
                'description' => 'Через сколько молчание узла полива, pH или EC считается проблемой.',
                'fields' => [
                    $sec('nodes_stale_online_sec', 'Числится в сети, но молчит', 'Узел помечен как онлайн, но не выходил на связь дольше указанного времени — в диагностике считается недоступным.'),
                    $sec('nodes_persistent_offline_sec', 'Давно не в сети', 'Узел offline дольше указанного времени — важность предупреждения повышается до критичной.'),
                ],
            ],
            [
                'key' => 'observability_levels',
                'label' => 'Датчики уровня баков',
                'description' => 'Через сколько отсутствие срабатывания поплавка считается проблемой наполнения или слива.',
                'fields' => [
                    $sec('level_clean_max_unlatched_sec', 'Чистый бак не наполнился', 'Идёт налив чистой воды, но верхний датчик бака не сработал дольше указанного времени (hint `level_clean_max_unlatched`).'),
                    $sec('level_solution_max_unlatched_sec', 'Бак раствора не наполнился', 'Идёт налив раствора, но верхний датчик бака не сработал дольше указанного времени (hint `level_solution_max_unlatched`).'),
                    $sec('level_solution_min_unlatched_sec', 'Раствор не сливается после полива', 'После полива нижний датчик бака раствора не сработал дольше указанного времени (hint `level_solution_min_unlatched`).'),
                ],
            ],
            [
                'key' => 'observability_stage_elapsed',
                'label' => 'Длительность этапов зоны',
                'description' => 'Сколько может длиться каждый этап работы зоны, прежде чем система предупредит оператора.',
                'fields' => $stageFields,
            ],
            [
                'key' => 'observability_scheduler',
                'label' => 'Задания планировщика',
                'description' => 'Через сколько задание из расписания считается зависшим на своём этапе.',
                'fields' => [
                    $sec('scheduler_intent_pending_warn_sec', 'Задание не взято в работу — предупреждение', 'Задание из расписания ждёт своей очереди дольше указанного времени (hint `scheduler_intent_pending`).'),
                    $sec('scheduler_intent_pending_critical_sec', 'Задание не взято в работу — критично', 'Порог, после которого ожидание в очереди считается критичным.'),
                    $sec('scheduler_intent_claimed_warn_sec', 'Задание взято, но не началось — предупреждение', 'Планировщик взял задание, но выполнение так и не стартовало дольше указанного времени (hint `scheduler_intent_claimed_stuck`).'),
                    $sec('scheduler_intent_claimed_critical_sec', 'Задание взято, но не началось — критично', 'Порог, после которого задержка старта считается критичной.'),
                    $sec('scheduler_intent_running_warn_sec', 'Задание выполняется слишком долго', 'Задание находится в работе дольше указанного времени (hint `scheduler_intent_running_stuck`, только предупреждение).', 60, 86400),
                    $sec('scheduler_intent_task_drift_warn_sec', 'Задание и задача движка разошлись', 'Планировщик считает задание выполняемым, а движок автоматики ещё не начал задачу (hint `scheduler_intent_task_drift`). Штатная переочередь двухбаковой схемы не учитывается.', 15, 600),
                ],
            ],
        ], ObservabilityThresholdsCatalog::NAMESPACE_KEY);
    }

    /**
     * @param  array<string, int>  $config
     */
    public static function validateConsistency(array $config): void
    {
        $pairs = [
            ['waiting_command_warn_sec', 'waiting_command_critical_sec'],
            ['task_dispatch_warn_sec', 'task_dispatch_critical_sec'],
            ['workflow_snapshot_stale_warn_sec', 'workflow_snapshot_stale_critical_sec'],
            ['correction_substep_warn_sec', 'correction_substep_critical_sec'],
            ['scheduler_intent_pending_warn_sec', 'scheduler_intent_pending_critical_sec'],
            ['scheduler_intent_claimed_warn_sec', 'scheduler_intent_claimed_critical_sec'],
        ];

        foreach (array_keys(self::stageKeys()) as $stage) {
            $pairs[] = ["stage_{$stage}_warn_sec", "stage_{$stage}_critical_sec"];
        }

        foreach ($pairs as [$warnKey, $criticalKey]) {
            $warn = (int) ($config[$warnKey] ?? 0);
            $critical = (int) ($config[$criticalKey] ?? 0);
            if ($warn >= $critical) {
                throw new InvalidArgumentException("Field {$warnKey} must be < {$criticalKey}.");
            }
        }
    }

    /**
     * @return array<string, string>
     */
    public static function stageKeys(): array
    {
        return [
            'startup' => 'Инициализация',
            'clean_fill_check' => 'Наполнение чистой водой',
            'solution_fill_check' => 'Наполнение раствором',
            'prepare_recirculation_check' => 'Подготовка рециркуляции',
            'irrigation_check' => 'Полив',
            'irrigation_recovery_check' => 'Recovery после полива',
            'await_ready' => 'Ожидание готовности',
            'decision_gate' => 'Решение о поливе',
        ];
    }

    /**
     * @return array{0:int,1:int}
     */
    private static function defaultStagePair(string $stage): array
    {
        return match ($stage) {
            'startup' => [120, 600],
            'clean_fill_check', 'irrigation_check' => [300, 1800],
            'solution_fill_check', 'prepare_recirculation_check', 'irrigation_recovery_check' => [600, 3600],
            'await_ready' => [300, 1800],
            'decision_gate' => [60, 300],
            default => [300, 1800],
        };
    }
}
