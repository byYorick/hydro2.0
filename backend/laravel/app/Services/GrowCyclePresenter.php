<?php

namespace App\Services;

use App\Models\GrowCycle;
use Carbon\Carbon;

class GrowCyclePresenter
{
    public function __construct(
        private GrowCycleService $growCycleService
    ) {
    }

    public function buildCycleDto(GrowCycle $cycle): array
    {
        $recipe = $cycle->recipe;
        $plantingAt = $cycle->planting_at ?? $cycle->started_at;

        if (!$recipe || !$plantingAt) {
            return [
                'cycle' => [
                    'id' => $cycle->id,
                    'status' => $cycle->status->value,
                ],
            ];
        }

        $stageMaps = $recipe->stageMaps()
            ->with('stageTemplate')
            ->orderBy('order_index')
            ->get();

        if ($stageMaps->isEmpty()) {
            $this->growCycleService->ensureRecipeStageMap($recipe);
            $stageMaps = $recipe->stageMaps()
                ->with('stageTemplate')
                ->orderBy('order_index')
                ->get();
        }

        $plantingDate = Carbon::parse($plantingAt);
        $now = now();
        $daysSincePlanting = $now->diffInDays($plantingDate);

        $stages = [];
        $currentStageIndex = -1;
        $overallProgress = 0;
        $totalDays = 0;

        foreach ($stageMaps as $map) {
            $duration = $map->end_offset_days
                ? ($map->end_offset_days - ($map->start_offset_days ?? 0))
                : ($map->stageTemplate->default_duration_days ?? 0);
            $totalDays += $duration;
        }

        foreach ($stageMaps as $index => $map) {
            $template = $map->stageTemplate;
            $startOffset = $map->start_offset_days ?? 0;
            $endOffset = $map->end_offset_days ?? $totalDays;

            $stageStart = $plantingDate->copy()->addDays($startOffset);
            $stageEnd = $endOffset ? $plantingDate->copy()->addDays($endOffset) : null;

            $stageDuration = $endOffset ? ($endOffset - $startOffset) : ($template->default_duration_days ?? 0);

            $state = 'UPCOMING';
            $pct = 0;

            if ($now >= $stageStart) {
                if ($stageEnd && $now >= $stageEnd) {
                    $state = 'DONE';
                    $pct = 100;
                } else {
                    $state = 'ACTIVE';
                    if ($stageDuration > 0) {
                        $elapsed = $now->diffInDays($stageStart);
                        $pct = min(100, max(0, ($elapsed / $stageDuration) * 100));
                    }
                }
            }

            if ($template->code === $cycle->current_stage_code) {
                $currentStageIndex = $index;
            }

            $stages[] = [
                'code' => $template->code,
                'name' => $template->name,
                'from' => $stageStart->toIso8601String(),
                'to' => $stageEnd?->toIso8601String(),
                'pct' => round($pct, 1),
                'state' => $state,
                'phase_indices' => $map->phase_indices ?? [],
            ];
        }

        if ($totalDays > 0 && $daysSincePlanting > 0) {
            $overallProgress = min(100, max(0, ($daysSincePlanting / $totalDays) * 100));
        }

        $currentStage = null;
        if ($cycle->current_stage_code) {
            $currentMap = $stageMaps->firstWhere('stageTemplate.code', $cycle->current_stage_code);
            if ($currentMap) {
                $currentTemplate = $currentMap->stageTemplate;
                $currentStage = [
                    'code' => $currentTemplate->code,
                    'name' => $currentTemplate->name,
                    'started_at' => $cycle->current_stage_started_at?->toIso8601String(),
                ];
            }
        }

        if (!$currentStage && !empty($stages)) {
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
