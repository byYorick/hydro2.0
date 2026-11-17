<?php

namespace App\Services;

use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;

/** Read-only evidence for the latest irrigation task, including completed skips. */
class IrrigationDecisionReadModel
{
    public function forZone(int $zoneId): ?array
    {
        $task = DB::table('ae_tasks')
            ->where('zone_id', $zoneId)
            ->where('task_type', 'irrigation_start')
            ->orderByDesc('id')
            ->first([
                'id', 'status', 'current_stage', 'created_at',
                'irrigation_decision_strategy', 'irrigation_decision_config',
                'irrigation_decision_outcome', 'irrigation_decision_reason_code',
                'irrigation_decision_degraded', 'irrigation_bundle_revision',
            ]);

        if ($task === null) {
            return null;
        }

        // Never mix observations from a previous task or an earlier retry with
        // the decision currently persisted on this task.
        $event = $task->irrigation_decision_outcome === null || $task->irrigation_decision_reason_code === null
            ? null : DB::table('zone_events')
            ->where('zone_id', $zoneId)
            ->where('type', 'IRRIGATION_DECISION_EVALUATED')
            ->where('created_at', '>=', $task->created_at)
            ->whereRaw("payload_json->>'task_id' = ?", [(string) $task->id])
            ->whereRaw("payload_json->>'outcome' = ?", [$task->irrigation_decision_outcome])
            ->whereRaw("payload_json->>'reason_code' = ?", [$task->irrigation_decision_reason_code])
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->first(['payload_json', 'created_at']);

        $evidence = $this->record($event?->payload_json);

        return [
            'task_id' => (int) $task->id,
            'task_status' => $task->status,
            'current_stage' => $task->current_stage,
            'created_at' => CarbonImmutable::parse($task->created_at, 'UTC')->toIso8601String(),
            'evaluated_at' => $event !== null ? CarbonImmutable::parse($event->created_at, 'UTC')->toIso8601String() : null,
            'strategy' => $task->irrigation_decision_strategy,
            'config' => $this->record($task->irrigation_decision_config),
            'outcome' => $task->irrigation_decision_outcome,
            'reason_code' => $task->irrigation_decision_reason_code,
            'degraded' => $task->irrigation_decision_degraded === null
                ? null : (bool) $task->irrigation_decision_degraded,
            'bundle_revision' => $task->irrigation_bundle_revision,
            'details' => is_array($evidence['details'] ?? null) ? $evidence['details'] : null,
        ];
    }

    private function record(mixed $value): ?array
    {
        if (is_string($value)) {
            $value = json_decode($value, true);
        }

        return is_array($value) ? $value : null;
    }
}
