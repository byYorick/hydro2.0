<?php

namespace App\Services;

use App\Models\Alert;
use App\Models\RecipeAnalytics;
use App\Models\TelemetrySample;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class RecipeAnalyticsService
{
    /**
     * Рассчитать и сохранить аналитику для зоны с активным циклом
     */
    public function calculateAndStore(int $zoneId, ?int $growCycleId = null): RecipeAnalytics
    {
        return DB::transaction(function () use ($zoneId, $growCycleId) {
            // Получаем активный цикл
            $cycle = $growCycleId
                ? GrowCycle::find($growCycleId)
                : GrowCycle::where('zone_id', $zoneId)
                    ->whereIn('status', [GrowCycleStatus::PLANNED, GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED])
                    ->first();

            if (! $cycle) {
                throw new \DomainException("No active grow cycle found for zone {$zoneId}");
            }

            $revision = $cycle->recipeRevision;
            if (! $revision) {
                throw new \DomainException("Grow cycle {$cycle->id} has no recipe revision");
            }

            $recipe = $revision->recipe;
            $zone = $cycle->zone;

            $startDate = $cycle->started_at ?? $cycle->planting_at ?? now();
            $endDate = now();

            // Получить все фазы ревизии рецепта
            $phases = $revision->phases()->orderBy('phase_index')->get();

            // Рассчитать отклонения pH и EC от целевых значений
            $phDeviations = [];
            $ecDeviations = [];

            foreach ($phases as $phase) {
                // Используем колонки вместо JSON targets
                $targetPh = $phase->ph_target;
                $targetEc = $phase->ec_target;

                if ($targetPh !== null && is_numeric($targetPh)) {
                    $phSamples = $this->getTelemetrySamples($zoneId, 'PH', $startDate, $endDate);
                    foreach ($phSamples as $sample) {
                        if (is_numeric($sample->value)) {
                            $phDeviations[] = abs($sample->value - floatval($targetPh));
                        }
                    }
                }

                if ($targetEc !== null && is_numeric($targetEc)) {
                    $ecSamples = $this->getTelemetrySamples($zoneId, 'EC', $startDate, $endDate);
                    foreach ($ecSamples as $sample) {
                        if (is_numeric($sample->value)) {
                            $ecDeviations[] = abs($sample->value - floatval($targetEc));
                        }
                    }
                }
            }

            $avgPhDeviation = ! empty($phDeviations) ? array_sum($phDeviations) / count($phDeviations) : null;
            $avgEcDeviation = ! empty($ecDeviations) ? array_sum($ecDeviations) / count($ecDeviations) : null;

            // Подсчитать количество аварий
            $alertsCount = Alert::where('zone_id', $zoneId)
                ->whereBetween('created_at', [$startDate, $endDate])
                ->count();

            // Рассчитать фактическую длительность (округляем до целого числа часов)
            $totalDurationHours = (int) round($startDate->diffInHours($endDate));

            // Рассчитать планируемую длительность (сумма duration_hours всех фаз)
            $plannedDurationHours = $phases->sum(function ($phase) {
                return $phase->duration_hours ?? ($phase->duration_days ?? 0) * 24;
            });

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
