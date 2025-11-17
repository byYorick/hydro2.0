<?php

namespace App\Services;

use App\Models\ZoneRecipeInstance;
use App\Models\RecipeAnalytics;
use App\Models\Alert;
use App\Models\TelemetrySample;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Carbon\Carbon;

class RecipeAnalyticsService
{
    /**
     * Рассчитать и сохранить аналитику для зоны с активным рецептом
     */
    public function calculateAndStore(int $zoneId, ?int $recipeInstanceId = null): RecipeAnalytics
    {
        return DB::transaction(function () use ($zoneId, $recipeInstanceId) {
            $instance = $recipeInstanceId
                ? ZoneRecipeInstance::find($recipeInstanceId)
                : ZoneRecipeInstance::where('zone_id', $zoneId)->first();

            if (!$instance) {
                throw new \DomainException("No active recipe instance found for zone {$zoneId}");
            }

            $recipe = $instance->recipe;
            $zone = $instance->zone;

            $startDate = $instance->started_at;
            $endDate = now();

            // Получить все фазы рецепта
            $phases = $recipe->phases()->orderBy('phase_index')->get();

            // Рассчитать отклонения pH и EC от целевых значений
            $phDeviations = [];
            $ecDeviations = [];

            foreach ($phases as $phase) {
                $targets = $phase->targets ?? [];
                $targetPh = is_array($targets) ? ($targets['ph'] ?? null) : null;
                $targetEc = is_array($targets) ? ($targets['ec'] ?? null) : null;

                if ($targetPh !== null) {
                    $targetPhVal = is_array($targetPh) ? ($targetPh['min'] ?? $targetPh['max'] ?? $targetPh) : $targetPh;
                    if (is_numeric($targetPhVal)) {
                        $phSamples = $this->getTelemetrySamples($zoneId, 'PH', $startDate, $endDate);
                        foreach ($phSamples as $sample) {
                            if (is_numeric($sample->value) && is_numeric($targetPhVal)) {
                                $phDeviations[] = abs($sample->value - floatval($targetPhVal));
                            }
                        }
                    }
                }

                if ($targetEc !== null) {
                    $targetEcVal = is_array($targetEc) ? ($targetEc['min'] ?? $targetEc['max'] ?? $targetEc) : $targetEc;
                    if (is_numeric($targetEcVal)) {
                        $ecSamples = $this->getTelemetrySamples($zoneId, 'EC', $startDate, $endDate);
                        foreach ($ecSamples as $sample) {
                            if (is_numeric($sample->value) && is_numeric($targetEcVal)) {
                                $ecDeviations[] = abs($sample->value - floatval($targetEcVal));
                            }
                        }
                    }
                }
            }

            $avgPhDeviation = !empty($phDeviations) ? array_sum($phDeviations) / count($phDeviations) : null;
            $avgEcDeviation = !empty($ecDeviations) ? array_sum($ecDeviations) / count($ecDeviations) : null;

            // Подсчитать количество аварий
            $alertsCount = Alert::where('zone_id', $zoneId)
                ->whereBetween('created_at', [$startDate, $endDate])
                ->count();

            // Рассчитать фактическую длительность
            $totalDurationHours = $startDate->diffInHours($endDate);

            // Рассчитать планируемую длительность
            $plannedDurationHours = $phases->sum('duration_hours');

            // Рассчитать оценку эффективности (0-100)
            // Базовые факторы: отклонения от целей, количество аварий, соблюдение сроков
            $efficiencyScore = $this->calculateEfficiencyScore(
                $avgPhDeviation,
                $avgEcDeviation,
                $alertsCount,
                $totalDurationHours,
                $plannedDurationHours
            );

            // Получить последний урожай для этой зоны (если есть)
            $lastHarvest = \App\Models\Harvest::where('zone_id', $zoneId)
                ->where('recipe_id', $recipe->id)
                ->latest('harvest_date')
                ->first();

            $finalYield = null;
            if ($lastHarvest) {
                $finalYield = [
                    'weight_kg' => $lastHarvest->yield_weight_kg,
                    'count' => $lastHarvest->yield_count,
                    'quality_score' => $lastHarvest->quality_score,
                ];
            }

            // Создать или обновить аналитику
            $analytics = RecipeAnalytics::updateOrCreate(
                [
                    'recipe_id' => $recipe->id,
                    'zone_id' => $zoneId,
                    'start_date' => $startDate,
                ],
                [
                    'end_date' => $endDate,
                    'total_duration_hours' => $totalDurationHours,
                    'avg_ph_deviation' => $avgPhDeviation,
                    'avg_ec_deviation' => $avgEcDeviation,
                    'alerts_count' => $alertsCount,
                    'final_yield' => $finalYield,
                    'efficiency_score' => $efficiencyScore,
                ]
            );

            Log::info('Recipe analytics calculated', [
                'recipe_id' => $recipe->id,
                'zone_id' => $zoneId,
                'efficiency_score' => $efficiencyScore,
            ]);

            return $analytics;
        });
    }

    /**
     * Получить выборки телеметрии для зоны
     */
    private function getTelemetrySamples(int $zoneId, string $metricType, Carbon $startDate, Carbon $endDate): \Illuminate\Database\Eloquent\Collection
    {
        return TelemetrySample::where('zone_id', $zoneId)
            ->where('metric_type', $metricType)
            ->whereBetween('ts', [$startDate, $endDate])
            ->get();
    }

    /**
     * Рассчитать оценку эффективности (0-100)
     */
    private function calculateEfficiencyScore(
        ?float $avgPhDeviation,
        ?float $avgEcDeviation,
        int $alertsCount,
        int $totalDurationHours,
        int $plannedDurationHours
    ): float {
        $score = 100.0;

        // Штраф за отклонения pH (максимум -30 баллов)
        if ($avgPhDeviation !== null) {
            $phPenalty = min(30.0, $avgPhDeviation * 10);
            $score -= $phPenalty;
        }

        // Штраф за отклонения EC (максимум -30 баллов)
        if ($avgEcDeviation !== null) {
            $ecPenalty = min(30.0, $avgEcDeviation * 15);
            $score -= $ecPenalty;
        }

        // Штраф за аварии (максимум -20 баллов)
        $alertsPenalty = min(20.0, $alertsCount * 2);
        $score -= $alertsPenalty;

        // Бонус/штраф за соблюдение сроков (максимум ±20 баллов)
        if ($plannedDurationHours > 0) {
            $durationRatio = $totalDurationHours / $plannedDurationHours;
            if ($durationRatio > 1.2) {
                // Задержка более 20% - штраф
                $score -= min(20.0, ($durationRatio - 1.2) * 50);
            } elseif ($durationRatio < 0.9) {
                // Завершение раньше более чем на 10% - бонус
                $score += min(10.0, (0.9 - $durationRatio) * 30);
            }
        }

        return max(0.0, min(100.0, $score));
    }
}

