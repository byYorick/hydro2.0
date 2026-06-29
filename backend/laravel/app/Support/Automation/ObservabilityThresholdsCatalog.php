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
                "{$stageLabel} — warning",
                "Hint `stage_elapsed_long` с severity warning, если этап «{$stageLabel}» активен дольше {$warnDefault} с. Не заменяет AE stage deadline.",
            );
            $stageFields[] = $sec(
                "stage_{$stage}_critical_sec",
                "{$stageLabel} — critical",
                "Hint `stage_elapsed_long` с severity critical, если этап «{$stageLabel}» активен дольше {$criticalDefault} с.",
            );
        }

        return FieldCatalogHelpBuilder::attachHelp([
            [
                'key' => 'observability_commands',
                'label' => 'Команды и dispatch AE3',
                'description' => 'Пороги для hints `waiting_command_stuck` и `task_dispatch_stuck` на live-path AE3 и при stale fallback Laravel.',
                'fields' => [
                    $sec('waiting_command_warn_sec', 'Waiting command — warning', 'Задача в `waiting_command` ждёт `command_response` дольше этого порога (сек). Считается от `task.updated_at`.'),
                    $sec('waiting_command_critical_sec', 'Waiting command — critical', 'Критичный порог для `waiting_command_stuck`. Должен быть больше warning.'),
                    $sec('task_dispatch_warn_sec', 'Task dispatch — warning', 'Задача в `pending`/`claimed` не переходит в `running` дольше порога (только AE3 live).'),
                    $sec('task_dispatch_critical_sec', 'Task dispatch — critical', 'Критичный порог для `task_dispatch_stuck`.'),
                ],
            ],
            [
                'key' => 'observability_runtime_diagnostics',
                'label' => 'Снимок workflow и коррекция',
                'description' => 'Диагностика устаревшего workflow snapshot и зависших подшагов коррекции pH/EC (только AE3 live).',
                'fields' => [
                    $sec('workflow_snapshot_stale_warn_sec', 'Workflow snapshot — warning', 'Активная фаза workflow, но `zone_workflow_state.updated_at` не обновлялся дольше порога → `workflow_snapshot_stale`.'),
                    $sec('workflow_snapshot_stale_critical_sec', 'Workflow snapshot — critical', 'Критичный порог для `workflow_snapshot_stale`.'),
                    $sec('correction_substep_warn_sec', 'Correction substep — warning', 'Подшаг `corr_wait_*` на активной задаче дольше порога → `correction_substep_stalled` warning.'),
                    $sec('correction_substep_critical_sec', 'Correction substep — critical', 'Критичный порог для `correction_substep_stalled`.'),
                ],
            ],
            [
                'key' => 'observability_nodes',
                'label' => 'Узлы зоны',
                'description' => 'Пороги для hint `nodes_offline` (required: irrig, ph, ec).',
                'fields' => [
                    $sec('nodes_stale_online_sec', 'Stale online', 'Узел в статусе online, но `last_seen` старше порога — считается stale для диагностики.'),
                    $sec('nodes_persistent_offline_sec', 'Persistent offline', 'Offline дольше порога повышает severity до critical (`persistent_offline`).'),
                ],
            ],
            [
                'key' => 'observability_levels',
                'label' => 'Датчики уровня баков',
                'description' => 'Пороги level-hints на релевантных check-стадиях при доступной telemetry (только AE3 live).',
                'fields' => [
                    $sec('level_clean_max_unlatched_sec', 'Clean max не подтверждён', 'На `clean_fill_check`/`clean_fill_start` без `clean_max` дольше порога → `level_clean_max_unlatched`.'),
                    $sec('level_solution_max_unlatched_sec', 'Solution max не подтверждён', 'На `solution_fill_check` без `solution_max` дольше порога → `level_solution_max_unlatched`.'),
                    $sec('level_solution_min_unlatched_sec', 'Solution min не подтверждён', 'На `irrigation_recovery_check` без `solution_min` дольше порога → `level_solution_min_unlatched`.'),
                ],
            ],
            [
                'key' => 'observability_stage_elapsed',
                'label' => 'Длительность этапов workflow',
                'description' => 'Per-stage пороги hint `stage_elapsed_long`. На stale cache Laravel использует те же значения из authority.',
                'fields' => $stageFields,
            ],
            [
                'key' => 'observability_scheduler',
                'label' => 'Планировщик Laravel',
                'description' => 'Пороги hints `scheduler_intent_*` из таблицы `zone_automation_intents` (только Laravel).',
                'fields' => [
                    $sec('scheduler_intent_pending_warn_sec', 'Intent pending — warning', 'Intent в `pending` старше порога → `scheduler_intent_pending` warning.'),
                    $sec('scheduler_intent_pending_critical_sec', 'Intent pending — critical', 'Критичный порог для `scheduler_intent_pending`.'),
                    $sec('scheduler_intent_claimed_warn_sec', 'Intent claimed — warning', 'Intent в `claimed` не перешёл в `running` → `scheduler_intent_claimed_stuck` warning.'),
                    $sec('scheduler_intent_claimed_critical_sec', 'Intent claimed — critical', 'Критичный порог для `scheduler_intent_claimed_stuck`.'),
                    $sec('scheduler_intent_running_warn_sec', 'Intent running — warning', 'Intent в `running` дольше порога → `scheduler_intent_running_stuck` (только warning).', 60, 86400),
                    $sec('scheduler_intent_task_drift_warn_sec', 'Intent/task drift — warning', 'Intent `running`, ae_task `pending` после `due_at` дольше порога → `scheduler_intent_task_drift` (исключает штатный two-tank requeue).', 15, 600),
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
