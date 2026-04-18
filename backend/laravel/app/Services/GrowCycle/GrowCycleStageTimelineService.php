<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Models\GrowCycle;
use App\Models\GrowStageTemplate;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use Carbon\Carbon;

/**
 * Строит timeline стадий grow cycle по фазам ревизии рецепта и шаблонам стадий,
 * вычисляет ETA сбора урожая (expected_harvest_at).
 */
class GrowCycleStageTimelineService
{
    public function computeExpectedHarvest(GrowCycle $cycle): void
    {
        $revision = $cycle->recipeRevision;
        if (! $revision) {
            return;
        }

        $plantingAt = $cycle->planting_at ?? $cycle->started_at;
        if (! $plantingAt) {
            return;
        }

        $timeline = $this->buildStageTimeline($revision);
        $totalHours = $timeline['total_hours'];
        if ($totalHours > 0) {
            $baseTime = $plantingAt instanceof Carbon ? $plantingAt->copy() : Carbon::parse($plantingAt);
            $expectedHarvestAt = $baseTime->addSeconds((int) round($totalHours * 3600));
            $cycle->update(['expected_harvest_at' => $expectedHarvestAt]);
        }
    }

    /**
     * @return array{segments: array<int, array{code: string, name: string, phase_indices: array<int>, duration_hours: float, ui_meta: array|null}>, total_hours: float}
     */
    public function buildStageTimeline(RecipeRevision $revision): array
    {
        $templates = GrowStageTemplate::orderBy('order_index')->get();
        if ($templates->isEmpty()) {
            $this->createDefaultStageTemplates();
            $templates = GrowStageTemplate::orderBy('order_index')->get();
        }

        $templatesById = $templates->keyBy('id');
        $templatesByCode = $templates->keyBy('code');

        $phases = $revision->phases()->orderBy('phase_index')->get();
        $segments = [];
        $totalSeconds = 0;

        foreach ($phases as $phase) {
            $template = $this->resolveStageTemplate($revision, $phase, $templatesById, $templatesByCode);
            $code = $template?->code ?? 'VEG';
            $name = $template?->name ?? 'Вегетация';
            $uiMeta = $template?->ui_meta;

            $durationHours = (float) ($phase->duration_hours
                ?? ($phase->duration_days ? $phase->duration_days * 24 : 0));
            $durationSeconds = (int) round($durationHours * 3600);
            $durationHoursNormalized = $durationSeconds / 3600;

            $totalSeconds += $durationSeconds;

            $lastIndex = count($segments) - 1;
            if ($lastIndex >= 0 && $segments[$lastIndex]['code'] === $code) {
                $segments[$lastIndex]['phase_indices'][] = $phase->phase_index;
                $segments[$lastIndex]['duration_hours'] += $durationHoursNormalized;
            } else {
                $segments[] = [
                    'code' => $code,
                    'name' => $name,
                    'phase_indices' => [$phase->phase_index],
                    'duration_hours' => $durationHoursNormalized,
                    'ui_meta' => $uiMeta,
                ];
            }
        }

        return [
            'segments' => $segments,
            'total_hours' => $totalSeconds / 3600,
        ];
    }

    private function resolveStageTemplate(
        RecipeRevision $revision,
        RecipeRevisionPhase $phase,
        \Illuminate\Support\Collection $templatesById,
        \Illuminate\Support\Collection $templatesByCode,
    ): ?GrowStageTemplate {
        if ($phase->stage_template_id && $templatesById->has($phase->stage_template_id)) {
            return $templatesById->get($phase->stage_template_id);
        }

        $code = $this->inferStageCode('', $phase->name ?? '', $phase->phase_index);

        return $templatesByCode->get($code)
            ?? $templatesByCode->get('VEG')
            ?? $templatesById->first();
    }

    private function inferStageCode(string $recipeName, string $phaseName, int $phaseIndex): string
    {
        $normalizedPhase = mb_strtolower(trim($phaseName));
        $normalizedRecipe = mb_strtolower(trim($recipeName));

        $mapping = [
            'GERMINATION' => ['проращ', 'germin'],
            'PLANTING' => ['посадка', 'посев', 'seed', 'семена', 'sowing'],
            'ROOTING' => ['укоренение', 'rooting', 'root', 'seedling', 'рассада', 'ростки', 'sprouting'],
            'VEG' => ['вега', 'вегетация', 'vegetative', 'veg', 'growth', 'рост', 'вегетативный', 'vegetation'],
            'FLOWER' => ['цветение', 'flowering', 'flower', 'bloom', 'blooming', 'цвет', 'floral'],
            'FRUIT' => ['плод', 'созрев', 'fruit'],
            'HARVEST' => ['сбор', 'harvest', 'finishing', 'finish', 'урожай', 'harvesting'],
        ];

        foreach ($mapping as $code => $keywords) {
            foreach ($keywords as $keyword) {
                if ($normalizedPhase !== '' && str_contains($normalizedPhase, $keyword)) {
                    return $code;
                }
            }
        }

        if (str_contains($normalizedRecipe, 'салат') || str_contains($normalizedRecipe, 'lettuce')) {
            return match ($phaseIndex) {
                0 => 'GERMINATION',
                1 => 'VEG',
                default => 'HARVEST',
            };
        }

        if (str_contains($normalizedRecipe, 'томат') || str_contains($normalizedRecipe, 'tomato')) {
            return match ($phaseIndex) {
                0 => 'GERMINATION',
                1 => 'VEG',
                2 => 'FLOWER',
                default => 'FRUIT',
            };
        }

        $fallbacks = ['PLANTING', 'ROOTING', 'VEG', 'FLOWER', 'FRUIT', 'HARVEST'];

        return $fallbacks[min($phaseIndex, count($fallbacks) - 1)] ?? 'VEG';
    }

    private function createDefaultStageTemplates(): void
    {
        $defaultStages = [
            ['name' => 'Посадка', 'code' => 'PLANTING', 'order' => 0, 'duration' => 1, 'color' => '#10b981', 'icon' => '🌱'],
            ['name' => 'Укоренение', 'code' => 'ROOTING', 'order' => 1, 'duration' => 7, 'color' => '#3b82f6', 'icon' => '🌿'],
            ['name' => 'Вега', 'code' => 'VEG', 'order' => 2, 'duration' => 21, 'color' => '#22c55e', 'icon' => '🌳'],
            ['name' => 'Цветение', 'code' => 'FLOWER', 'order' => 3, 'duration' => 14, 'color' => '#f59e0b', 'icon' => '🌸'],
            ['name' => 'Плодоношение', 'code' => 'FRUIT', 'order' => 4, 'duration' => 21, 'color' => '#ef4444', 'icon' => '🍅'],
            ['name' => 'Сбор', 'code' => 'HARVEST', 'order' => 5, 'duration' => 1, 'color' => '#8b5cf6', 'icon' => '✂️'],
        ];

        foreach ($defaultStages as $stage) {
            GrowStageTemplate::create([
                'name' => $stage['name'],
                'code' => $stage['code'],
                'order_index' => $stage['order'],
                'default_duration_days' => $stage['duration'],
                'ui_meta' => [
                    'color' => $stage['color'],
                    'icon' => $stage['icon'],
                    'description' => $stage['name'],
                ],
            ]);
        }
    }
}
