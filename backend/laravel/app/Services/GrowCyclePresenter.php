<?php

namespace App\Services;

use App\Models\GrowCycle;
use Carbon\Carbon;

class GrowCyclePresenter
{
    public function __construct(
        private GrowCycleService $growCycleService
    ) {}

    public function buildCycleDto(GrowCycle $cycle): array
    {
        $plantingAt = $cycle->planting_at ?? $cycle->started_at;

        $revision = $cycle->recipeRevision;
        if (! $revision || ! $plantingAt) {
            return [
                'cycle' => [
                    'id' => $cycle->id,
                    'status' => $cycle->status->value,
                ],
            ];
        }

        $timeline = $this->growCycleService->buildStageTimeline($revision);
        $segments = $timeline['segments'];
        $totalHours = $timeline['total_hours'];

        $plantingDate = Carbon::parse($plantingAt);
        $now = now();
        $hoursSincePlanting = $now->diffInHours($plantingDate, false);

        $stages = [];
        $currentStageIndex = -1;
        $overallProgress = 0;
        $currentPhaseIndex = $cycle->currentPhase?->phase_index;
        $cumulativeHours = 0.0;

        foreach ($segments as $index => $segment) {
            $stageStart = $plantingDate->copy()->addHours($cumulativeHours);
            $stageEnd = $segment['duration_hours'] > 0
                ? $stageStart->copy()->addHours($segment['duration_hours'])
                : null;

            $state = 'UPCOMING';
            $pct = 0;

            if ($now >= $stageStart) {
                if ($stageEnd && $now >= $stageEnd) {
                    $state = 'DONE';
                    $pct = 100;
                } else {
                    $state = 'ACTIVE';
                    if ($segment['duration_hours'] > 0) {
                        $elapsed = max(0, $now->diffInHours($stageStart, false));
                        $pct = min(100, max(0, ($elapsed / $segment['duration_hours']) * 100));
                    }
                }
            }

            if ($currentPhaseIndex !== null && in_array($currentPhaseIndex, $segment['phase_indices'], true)) {
                $currentStageIndex = $index;
            }

            $stages[] = [
                'code' => $segment['code'],
                'name' => $segment['name'],
                'from' => $stageStart->toIso8601String(),
                'to' => $stageEnd?->toIso8601String(),
                'pct' => round($pct, 1),
                'state' => $state,
                'phase_indices' => $segment['phase_indices'],
            ];

            $cumulativeHours += $segment['duration_hours'];
        }

        if ($totalHours > 0 && $hoursSincePlanting > 0) {
            $overallProgress = min(100, max(0, ($hoursSincePlanting / $totalHours) * 100));
        }

        $currentStage = null;
        if ($currentStageIndex >= 0 && isset($stages[$currentStageIndex])) {
            $currentStage = [
                'code' => $stages[$currentStageIndex]['code'],
                'name' => $stages[$currentStageIndex]['name'],
                'started_at' => $stages[$currentStageIndex]['from'],
            ];
        }

        if (! $currentStage) {
            foreach ($stages as $stage) {
                if ($stage['state'] === 'ACTIVE') {
                    $currentStage = [
                        'code' => $stage['code'],
                        'name' => $stage['name'],
                        'started_at' => $stage['from'],
                    ];
                    break;
                }
            }
        }

        return [
            'cycle' => [
                'id' => $cycle->id,
                'status' => $cycle->status->value,
                'planting_at' => $plantingDate->toIso8601String(),
                'expected_harvest_at' => $cycle->expected_harvest_at?->toIso8601String(),
                'current_stage' => $currentStage,
                'progress' => [
                    'overall_pct' => round($overallProgress, 1),
                    'stage_pct' => $currentStageIndex >= 0 ? $stages[$currentStageIndex]['pct'] : 0,
                ],
                'stages' => $stages,
            ],
        ];
    }
}
