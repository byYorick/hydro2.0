<?php

namespace App\Services;

use App\Models\GrowCycle;
use App\Models\GrowCycleOverride;
use App\Models\GrowCyclePhase;
use App\Models\RecipeRevisionPhase;
use Carbon\Carbon;
use Illuminate\Support\Collection;

class EffectiveTargetsService
{
    /**
     * Получить эффективные целевые параметры для цикла выращивания
     * 
     * @param int $growCycleId
     * @return array Структурированный JSON согласно контракту
     * @throws \Illuminate\Database\Eloquent\ModelNotFoundException
     */
    public function getEffectiveTargets(int $growCycleId): array
    {
        $cycle = GrowCycle::with([
            'currentPhase.recipeRevisionPhase.stageTemplate', // Для снапшотов получаем stageTemplate через recipeRevisionPhase
            'recipeRevision',
            'zone',
        ])->findOrFail($growCycleId);

        if (!$cycle->currentPhase) {
            throw new \RuntimeException("Grow cycle {$growCycleId} has no current phase");
        }

        $phase = $cycle->currentPhase;
        
        // Получаем базовые параметры из фазы
        $phaseTargets = $this->extractPhaseTargets($phase);
        
        // Получаем активные перекрытия
        $overrides = $this->getActiveOverrides($cycle);
        
        // Сливаем перекрытия с базовыми параметрами
        $effectiveTargets = $this->mergeOverrides($phaseTargets, $overrides);
        
        // Вычисляем due_at для фазы
        $phaseDueAt = $this->calculatePhaseDueAt($cycle, $phase);
        
        // Формируем метаданные фазы
        // Для снапшота получаем stageTemplate через recipeRevisionPhase, для шаблона напрямую
        $stageTemplate = $phase instanceof GrowCyclePhase 
            ? $phase->recipeRevisionPhase?->stageTemplate 
            : $phase->stageTemplate;
        
        $phaseMeta = [
            'id' => $phase->id,
            'code' => $stageTemplate?->code ?? 'UNKNOWN',
            'name' => $phase->name,
            'started_at' => $cycle->phase_started_at?->toIso8601String(),
            'due_at' => $phaseDueAt?->toIso8601String(),
            'progress_model' => $phase->progress_model,
        ];

        // Очищаем null значения из targets для чистого JSON
        $effectiveTargets = $this->cleanNullValues($effectiveTargets);

        return [
            'cycle_id' => $cycle->id,
            'zone_id' => $cycle->zone_id,
            'phase' => $phaseMeta,
            'targets' => $effectiveTargets,
        ];
    }

    /**
     * Получить эффективные параметры для нескольких циклов (batch)
     * 
     * @param array $growCycleIds
     * @return array Массив результатов, ключ - grow_cycle_id
     */
    public function getEffectiveTargetsBatch(array $growCycleIds): array
    {
        $results = [];
        
        foreach ($growCycleIds as $cycleId) {
            try {
                $results[$cycleId] = $this->getEffectiveTargets($cycleId);
            } catch (\Exception $e) {
                $results[$cycleId] = [
                    'error' => $e->getMessage(),
                ];
            }
        }
        
        return $results;
    }

    /**
     * Извлечь целевые параметры из фазы (снапшот или шаблон)
     * 
     * @param GrowCyclePhase|RecipeRevisionPhase $phase
     */
    protected function extractPhaseTargets($phase): array
    {
        $targets = [];

        // pH параметры
        if ($phase->ph_target !== null) {
            $targets['ph'] = [
                'target' => (float) $phase->ph_target,
                'min' => $phase->ph_min ? (float) $phase->ph_min : null,
                'max' => $phase->ph_max ? (float) $phase->ph_max : null,
            ];
        }

        // EC параметры
        if ($phase->ec_target !== null) {
            $targets['ec'] = [
                'target' => (float) $phase->ec_target,
                'min' => $phase->ec_min ? (float) $phase->ec_min : null,
                'max' => $phase->ec_max ? (float) $phase->ec_max : null,
            ];
        }

        // Полив
        if ($phase->irrigation_mode !== null) {
            $targets['irrigation'] = [
                'mode' => $phase->irrigation_mode,
                'interval_sec' => $phase->irrigation_interval_sec,
                'duration_sec' => $phase->irrigation_duration_sec,
            ];
        }

        // Туман
        if ($phase->mist_interval_sec !== null || $phase->mist_duration_sec !== null) {
            $targets['mist'] = [
                'interval_sec' => $phase->mist_interval_sec,
                'duration_sec' => $phase->mist_duration_sec,
                'mode' => $phase->mist_mode,
            ];
        }

        // Освещение
        if ($phase->lighting_photoperiod_hours !== null) {
            $targets['lighting'] = [
                'photoperiod_hours' => $phase->lighting_photoperiod_hours,
                'start_time' => $phase->lighting_start_time 
                    ? (is_string($phase->lighting_start_time) 
                        ? $phase->lighting_start_time 
                        : Carbon::parse($phase->lighting_start_time)->format('H:i:s'))
                    : null,
            ];
        }

        // Климат (запрос к климату теплицы)
        $climateRequest = [];
        if ($phase->temp_air_target !== null) {
            $climateRequest['temp_air_target'] = (float) $phase->temp_air_target;
        }
        if ($phase->humidity_target !== null) {
            $climateRequest['humidity_target'] = (float) $phase->humidity_target;
        }
        if ($phase->co2_target !== null) {
            $climateRequest['co2_target'] = $phase->co2_target;
        }
        if (!empty($climateRequest)) {
            $targets['climate_request'] = $climateRequest;
        }

        // Расширения (нестандартные параметры)
        if ($phase->extensions) {
            $targets['extensions'] = $phase->extensions;
        }

        return $targets;
    }

    /**
     * Получить активные перекрытия для цикла
     */
    protected function getActiveOverrides(GrowCycle $cycle): Collection
    {
        return GrowCycleOverride::where('grow_cycle_id', $cycle->id)
            ->where('is_active', true)
            ->get()
            ->filter(function ($override) {
                return $override->isCurrentlyActive();
            });
    }

    /**
     * Слить перекрытия с базовыми параметрами
     */
    protected function mergeOverrides(array $phaseTargets, Collection $overrides): array
    {
        $effective = $phaseTargets;

        foreach ($overrides as $override) {
            $parameter = $override->parameter;
            $value = $override->getTypedValue();

            // Поддержка вложенных параметров (например, ph.target, irrigation.interval_sec)
            if (str_contains($parameter, '.')) {
                [$section, $key] = explode('.', $parameter, 2);
                
                if (!isset($effective[$section])) {
                    $effective[$section] = [];
                }
                
                $effective[$section][$key] = $value;
            } else {
                // Простые параметры (если есть такие)
                $effective[$parameter] = $value;
            }
        }

        return $effective;
    }

    /**
     * Вычислить due_at для фазы на основе progress_model
     * 
     * @param GrowCycle $cycle
     * @param GrowCyclePhase|RecipeRevisionPhase $phase
     */
    protected function calculatePhaseDueAt(GrowCycle $cycle, $phase): ?Carbon
    {
        if (!$cycle->phase_started_at) {
            return null;
        }

        // phase_started_at уже cast в datetime, но parse безопасно работает и с Carbon объектами
        $startedAt = $cycle->phase_started_at instanceof Carbon 
            ? $cycle->phase_started_at 
            : Carbon::parse($cycle->phase_started_at);

        // Простая модель по времени
        if ($phase->progress_model === 'TIME' || !$phase->progress_model) {
            if ($phase->duration_hours) {
                return $startedAt->copy()->addHours($phase->duration_hours);
            }
            if ($phase->duration_days) {
                return $startedAt->copy()->addDays($phase->duration_days);
            }
        }

        // Коррекция по температуре (упрощенная)
        if ($phase->progress_model === 'TIME_WITH_TEMP_CORRECTION') {
            $baseDuration = $phase->duration_hours ?? ($phase->duration_days * 24);
            $speedFactor = $this->calculateSpeedFactor($cycle, $phase);
            
            if ($baseDuration && $speedFactor) {
                return $startedAt->copy()->addHours($baseDuration / $speedFactor);
            }
        }

        // GDD (градусо-дни) - требует накопления данных
        if ($phase->progress_model === 'GDD' && $phase->target_gdd) {
            // TODO: Реализовать после добавления Phase Progress Engine
            // Пока возвращаем null, будет вычисляться отдельным сервисом
        }

        return null;
    }

    /**
     * Вычислить коэффициент скорости роста на основе температуры
     * 
     * @param GrowCycle $cycle
     * @param GrowCyclePhase|RecipeRevisionPhase $phase
     */
    protected function calculateSpeedFactor(GrowCycle $cycle, $phase): ?float
    {
        $progressMeta = $cycle->progress_meta ?? [];
        $avgTemp24h = $progressMeta['temp_avg_24h'] ?? null;
        $baseTemp = $phase->base_temp_c;

        if (!$avgTemp24h || !$baseTemp) {
            return null;
        }

        // Упрощенная формула: скорость пропорциональна разнице температур
        // Более точная формула будет в Phase Progress Engine
        // Формула: +1% скорости на каждые 1°C выше базовой температуры
        if ($avgTemp24h > $baseTemp) {
            $tempDiff = $avgTemp24h - $baseTemp;
            return 1.0 + ($tempDiff * 0.01); // +1% на каждый градус выше базовой
        }

        return 1.0;
    }

    /**
     * Очистить null значения из массива targets (рекурсивно)
     */
    protected function cleanNullValues(array $array): array
    {
        $cleaned = [];
        
        foreach ($array as $key => $value) {
            if (is_array($value)) {
                $cleanedValue = $this->cleanNullValues($value);
                // Не добавляем пустые массивы
                if (!empty($cleanedValue)) {
                    $cleaned[$key] = $cleanedValue;
                }
            } elseif ($value !== null) {
                $cleaned[$key] = $value;
            }
        }
        
        return $cleaned;
    }
}

