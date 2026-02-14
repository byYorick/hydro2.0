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
    public function __construct(
        private readonly ZoneAutomationLogicProfileService $automationLogicProfiles,
    ) {
    }

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
            'currentPhase.recipeRevisionPhase.npkProduct',
            'currentPhase.recipeRevisionPhase.calciumProduct',
            'currentPhase.recipeRevisionPhase.magnesiumProduct',
            'currentPhase.recipeRevisionPhase.microProduct',
            'currentPhase.npkProduct',
            'currentPhase.calciumProduct',
            'currentPhase.magnesiumProduct',
            'currentPhase.microProduct',
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

        // Накладываем runtime-настройки автоматики из активного profile-mode зоны.
        $runtimeProfile = $this->resolveRuntimeProfileForCycle($cycle);
        $effectiveTargets = $this->mergeCycleSettings($effectiveTargets, $runtimeProfile['subsystems'] ?? null);
        $effectiveTargets = $this->appendRuntimeProfileMeta($effectiveTargets, $runtimeProfile);
        
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
        $recipePhase = $phase instanceof GrowCyclePhase ? $phase->recipeRevisionPhase : null;

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

        // Компоненты питания для EC-дозирования (4-помповая схема)
        $nutrientProgramCode = $phase->nutrient_program_code ?? $recipePhase?->nutrient_program_code;
        $nutrientMode = $phase->nutrient_mode ?? $recipePhase?->nutrient_mode;
        $nutrientNpkRatioPct = $phase->nutrient_npk_ratio_pct ?? $recipePhase?->nutrient_npk_ratio_pct;
        $nutrientNpkDoseMlL = $phase->nutrient_npk_dose_ml_l ?? $recipePhase?->nutrient_npk_dose_ml_l;
        $nutrientNpkProductId = $phase->nutrient_npk_product_id ?? $recipePhase?->nutrient_npk_product_id;
        $nutrientCalciumRatioPct = $phase->nutrient_calcium_ratio_pct ?? $recipePhase?->nutrient_calcium_ratio_pct;
        $nutrientCalciumDoseMlL = $phase->nutrient_calcium_dose_ml_l ?? $recipePhase?->nutrient_calcium_dose_ml_l;
        $nutrientCalciumProductId = $phase->nutrient_calcium_product_id ?? $recipePhase?->nutrient_calcium_product_id;
        $nutrientMagnesiumRatioPct = $phase->nutrient_magnesium_ratio_pct ?? $recipePhase?->nutrient_magnesium_ratio_pct;
        $nutrientMagnesiumDoseMlL = $phase->nutrient_magnesium_dose_ml_l ?? $recipePhase?->nutrient_magnesium_dose_ml_l;
        $nutrientMagnesiumProductId = $phase->nutrient_magnesium_product_id ?? $recipePhase?->nutrient_magnesium_product_id;
        $nutrientMicroRatioPct = $phase->nutrient_micro_ratio_pct ?? $recipePhase?->nutrient_micro_ratio_pct;
        $nutrientMicroDoseMlL = $phase->nutrient_micro_dose_ml_l ?? $recipePhase?->nutrient_micro_dose_ml_l;
        $nutrientMicroProductId = $phase->nutrient_micro_product_id ?? $recipePhase?->nutrient_micro_product_id;
        $nutrientDoseDelaySec = $phase->nutrient_dose_delay_sec ?? $recipePhase?->nutrient_dose_delay_sec;
        $nutrientEcStopTolerance = $phase->nutrient_ec_stop_tolerance ?? $recipePhase?->nutrient_ec_stop_tolerance;
        $nutrientSolutionVolumeL = $phase->nutrient_solution_volume_l ?? $recipePhase?->nutrient_solution_volume_l;

        $npkProduct = $phase->npkProduct ?? $recipePhase?->npkProduct;
        $calciumProduct = $phase->calciumProduct ?? $recipePhase?->calciumProduct;
        $magnesiumProduct = $phase->magnesiumProduct ?? $recipePhase?->magnesiumProduct;
        $microProduct = $phase->microProduct ?? $recipePhase?->microProduct;

        $nutrition = [
            'program_code' => $nutrientProgramCode,
            'mode' => $nutrientMode,
            'components' => [
                'npk' => [
                    'ratio_pct' => $nutrientNpkRatioPct !== null ? (float) $nutrientNpkRatioPct : null,
                    'dose_ml_per_l' => $nutrientNpkDoseMlL !== null ? (float) $nutrientNpkDoseMlL : null,
                    'product_id' => $nutrientNpkProductId,
                    'product_name' => $npkProduct?->name,
                    'manufacturer' => $npkProduct?->manufacturer,
                ],
                'calcium' => [
                    'ratio_pct' => $nutrientCalciumRatioPct !== null ? (float) $nutrientCalciumRatioPct : null,
                    'dose_ml_per_l' => $nutrientCalciumDoseMlL !== null ? (float) $nutrientCalciumDoseMlL : null,
                    'product_id' => $nutrientCalciumProductId,
                    'product_name' => $calciumProduct?->name,
                    'manufacturer' => $calciumProduct?->manufacturer,
                ],
                'magnesium' => [
                    'ratio_pct' => $nutrientMagnesiumRatioPct !== null ? (float) $nutrientMagnesiumRatioPct : null,
                    'dose_ml_per_l' => $nutrientMagnesiumDoseMlL !== null ? (float) $nutrientMagnesiumDoseMlL : null,
                    'product_id' => $nutrientMagnesiumProductId,
                    'product_name' => $magnesiumProduct?->name,
                    'manufacturer' => $magnesiumProduct?->manufacturer,
                ],
                'micro' => [
                    'ratio_pct' => $nutrientMicroRatioPct !== null ? (float) $nutrientMicroRatioPct : null,
                    'dose_ml_per_l' => $nutrientMicroDoseMlL !== null ? (float) $nutrientMicroDoseMlL : null,
                    'product_id' => $nutrientMicroProductId,
                    'product_name' => $microProduct?->name,
                    'manufacturer' => $microProduct?->manufacturer,
                ],
            ],
            'dose_delay_sec' => $nutrientDoseDelaySec,
            'ec_stop_tolerance' => $nutrientEcStopTolerance !== null ? (float) $nutrientEcStopTolerance : null,
            'solution_volume_l' => $nutrientSolutionVolumeL !== null ? (float) $nutrientSolutionVolumeL : null,
        ];
        $nutrition = $this->cleanNullValues($nutrition);
        if (!empty($nutrition)) {
            $targets['nutrition'] = $nutrition;
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

    protected function resolveRuntimeProfileForCycle(GrowCycle $cycle): ?array
    {
        $profile = $this->automationLogicProfiles->resolveActiveProfileForZone($cycle->zone_id);
        if ($profile && is_array($profile->subsystems) && !empty($profile->subsystems)) {
            return [
                'source' => 'zone_automation_logic_profile',
                'mode' => $profile->mode,
                'updated_at' => $profile->updated_at?->toIso8601String(),
                'subsystems' => $profile->subsystems,
            ];
        }

        return null;
    }

    /**
     * Наложить runtime-настройки подсистем на effective targets.
     * Приоритет: phase -> overrides -> runtime settings.
     */
    protected function mergeCycleSettings(array $targets, mixed $subsystems): array
    {
        if (!is_array($subsystems) || empty($subsystems)) {
            return $targets;
        }

        $targets = $this->mergeIrrigationSubsystem($targets, $subsystems);
        $targets = $this->mergeLightingSubsystem($targets, $subsystems);
        $targets = $this->mergeClimateSubsystem($targets, $subsystems);
        $targets = $this->mergeDiagnosticsSubsystem($targets, $subsystems);
        $targets = $this->mergeSolutionSubsystem($targets, $subsystems);
        $targets = $this->appendSubsystemsToExtensions($targets, $subsystems);

        return $targets;
    }

    protected function appendRuntimeProfileMeta(array $targets, ?array $runtimeProfile): array
    {
        if (!is_array($runtimeProfile) || empty($runtimeProfile)) {
            return $targets;
        }

        $extensions = is_array($targets['extensions'] ?? null) ? $targets['extensions'] : [];
        $extensions['automation_logic'] = [
            'source' => $runtimeProfile['source'] ?? null,
            'mode' => $runtimeProfile['mode'] ?? null,
            'updated_at' => $runtimeProfile['updated_at'] ?? null,
        ];
        $targets['extensions'] = $extensions;

        return $targets;
    }

    protected function mergePhSubsystem(array $targets, array $subsystems): array
    {
        $enabled = $this->extractSubsystemEnabled($subsystems, 'ph');
        $phTargets = $this->extractSubsystemTargets($subsystems, 'ph');
        if ($enabled !== true || !is_array($phTargets)) {
            return $targets;
        }

        $ph = is_array($targets['ph'] ?? null) ? $targets['ph'] : [];
        $targetValue = $this->toFloat($phTargets['target'] ?? null);
        $minValue = $this->toFloat($phTargets['min'] ?? null);
        $maxValue = $this->toFloat($phTargets['max'] ?? null);

        if ($targetValue !== null) {
            $ph['target'] = $targetValue;
        }
        if ($minValue !== null) {
            $ph['min'] = $minValue;
        }
        if ($maxValue !== null) {
            $ph['max'] = $maxValue;
        }

        if (!empty($ph)) {
            $targets['ph'] = $ph;
        }

        return $targets;
    }

    protected function mergeEcSubsystem(array $targets, array $subsystems): array
    {
        $enabled = $this->extractSubsystemEnabled($subsystems, 'ec');
        $ecTargets = $this->extractSubsystemTargets($subsystems, 'ec');
        if ($enabled !== true || !is_array($ecTargets)) {
            return $targets;
        }

        $ec = is_array($targets['ec'] ?? null) ? $targets['ec'] : [];
        $targetValue = $this->toFloat($ecTargets['target'] ?? null);
        $minValue = $this->toFloat($ecTargets['min'] ?? null);
        $maxValue = $this->toFloat($ecTargets['max'] ?? null);

        if ($targetValue !== null) {
            $ec['target'] = $targetValue;
        }
        if ($minValue !== null) {
            $ec['min'] = $minValue;
        }
        if ($maxValue !== null) {
            $ec['max'] = $maxValue;
        }

        if (!empty($ec)) {
            $targets['ec'] = $ec;
        }

        return $targets;
    }

    protected function mergeIrrigationSubsystem(array $targets, array $subsystems): array
    {
        $enabled = $this->extractSubsystemEnabled($subsystems, 'irrigation');
        $irrigationTargets = $this->extractSubsystemTargets($subsystems, 'irrigation');
        if ($enabled === null && !is_array($irrigationTargets)) {
            return $targets;
        }

        $irrigation = is_array($targets['irrigation'] ?? null) ? $targets['irrigation'] : [];

        if (is_array($irrigationTargets)) {
            $intervalSec = $this->resolveIntervalSeconds($irrigationTargets);
            if ($intervalSec !== null) {
                $irrigation['interval_sec'] = $intervalSec;
            }

            $durationSec = $this->resolveDurationSeconds($irrigationTargets);
            if ($durationSec !== null) {
                $irrigation['duration_sec'] = $durationSec;
            }

            if (isset($irrigationTargets['system_type']) && is_string($irrigationTargets['system_type'])) {
                $systemType = trim((string) $irrigationTargets['system_type']);
                if ($systemType !== '') {
                    $irrigation['system_type'] = $systemType;
                }
            }

            if (isset($irrigationTargets['execution']) && is_array($irrigationTargets['execution'])) {
                $irrigation = $this->mergeTaskExecution($irrigation, $irrigationTargets['execution']);
            }
        }

        if ($enabled === false) {
            $irrigation = $this->mergeTaskExecution($irrigation, ['force_skip' => true]);
        } elseif ($enabled === true) {
            $irrigation = $this->mergeTaskExecution($irrigation, ['force_skip' => false]);
        }

        if (!empty($irrigation)) {
            $targets['irrigation'] = $irrigation;
        }

        return $targets;
    }

    protected function mergeLightingSubsystem(array $targets, array $subsystems): array
    {
        $enabled = $this->extractSubsystemEnabled($subsystems, 'lighting');
        $lightingTargets = $this->extractSubsystemTargets($subsystems, 'lighting');
        if ($enabled === null && !is_array($lightingTargets)) {
            return $targets;
        }

        $lighting = is_array($targets['lighting'] ?? null) ? $targets['lighting'] : [];

        if (is_array($lightingTargets)) {
            $photoperiodHours = $this->toFloat($lightingTargets['photoperiod_hours'] ?? null);
            if ($photoperiodHours === null && is_array($lightingTargets['photoperiod'] ?? null)) {
                $photoperiodHours = $this->toFloat($lightingTargets['photoperiod']['hours_on'] ?? null);
            }
            if ($photoperiodHours !== null) {
                $lighting['photoperiod_hours'] = $photoperiodHours;
            }

            $startTime = $this->resolveScheduleStartTime($lightingTargets['schedule'] ?? null);
            if ($startTime === null) {
                $startTime = $this->normalizeTimeString($lightingTargets['start_time'] ?? null);
            }
            if ($startTime !== null) {
                $lighting['start_time'] = $startTime;
            }

            $intervalSec = $this->resolveIntervalSeconds($lightingTargets);
            if ($intervalSec !== null) {
                $lighting['interval_sec'] = $intervalSec;
            }

            if (isset($lightingTargets['execution']) && is_array($lightingTargets['execution'])) {
                $lighting = $this->mergeTaskExecution($lighting, $lightingTargets['execution']);
            }
        }

        if ($enabled === false) {
            $lighting = $this->mergeTaskExecution($lighting, ['force_skip' => true]);
        } elseif ($enabled === true) {
            $lighting = $this->mergeTaskExecution($lighting, ['force_skip' => false]);
        }

        if (!empty($lighting)) {
            $targets['lighting'] = $lighting;
        }

        return $targets;
    }

    protected function mergeClimateSubsystem(array $targets, array $subsystems): array
    {
        $enabled = $this->extractSubsystemEnabled($subsystems, 'climate');
        $climateTargets = $this->extractSubsystemTargets($subsystems, 'climate');
        if ($enabled === null && !is_array($climateTargets)) {
            return $targets;
        }

        if (is_array($climateTargets)) {
            $climateRequest = is_array($targets['climate_request'] ?? null) ? $targets['climate_request'] : [];

            $dayTemp = $this->toFloat($climateTargets['temperature']['day'] ?? null);
            if ($dayTemp !== null) {
                $climateRequest['temp_air_target'] = $dayTemp;
            }

            $dayHumidity = $this->toFloat($climateTargets['humidity']['day'] ?? null);
            if ($dayHumidity !== null) {
                $climateRequest['humidity_target'] = $dayHumidity;
            }

            if (!empty($climateRequest)) {
                $targets['climate_request'] = $climateRequest;
            }
        }

        // Scheduler использует task_type=ventilation для периодического контроля климата.
        $ventilation = is_array($targets['ventilation'] ?? null) ? $targets['ventilation'] : [];
        if (is_array($climateTargets)) {
            $intervalSec = $this->resolveIntervalSeconds($climateTargets);
            if ($intervalSec !== null) {
                $ventilation['interval_sec'] = $intervalSec;
            }
            if (isset($climateTargets['execution']) && is_array($climateTargets['execution'])) {
                $ventilation = $this->mergeTaskExecution($ventilation, $climateTargets['execution']);
            }
        }

        if ($enabled === false) {
            $ventilation = $this->mergeTaskExecution($ventilation, ['force_skip' => true]);
        } elseif ($enabled === true) {
            $ventilation = $this->mergeTaskExecution($ventilation, ['force_skip' => false]);
        }

        if (!empty($ventilation)) {
            $targets['ventilation'] = $ventilation;
        }

        return $targets;
    }

    protected function mergeDiagnosticsSubsystem(array $targets, array $subsystems): array
    {
        $enabled = $this->extractSubsystemEnabled($subsystems, 'diagnostics');
        $diagnosticsTargets = $this->extractSubsystemTargets($subsystems, 'diagnostics');
        if ($enabled === null && !is_array($diagnosticsTargets)) {
            return $targets;
        }

        $diagnostics = is_array($targets['diagnostics'] ?? null) ? $targets['diagnostics'] : [];

        if (is_array($diagnosticsTargets)) {
            $intervalSec = $this->resolveIntervalSeconds($diagnosticsTargets);
            if ($intervalSec !== null) {
                $diagnostics['interval_sec'] = $intervalSec;
            }

            $executionPatch = [];
            if (isset($diagnosticsTargets['execution']) && is_array($diagnosticsTargets['execution'])) {
                $executionPatch = $diagnosticsTargets['execution'];
            }

            if (isset($diagnosticsTargets['workflow']) && is_string($diagnosticsTargets['workflow'])) {
                $workflow = trim((string) $diagnosticsTargets['workflow']);
                if ($workflow !== '') {
                    $executionPatch['workflow'] = $workflow;
                }
            }

            if (isset($diagnosticsTargets['required_node_types']) && is_array($diagnosticsTargets['required_node_types'])) {
                $executionPatch['required_node_types'] = array_values($diagnosticsTargets['required_node_types']);
            }

            $cleanTankThreshold = $this->toFloat($diagnosticsTargets['clean_tank_full_threshold'] ?? null);
            if ($cleanTankThreshold !== null) {
                $executionPatch['clean_tank_full_threshold'] = $cleanTankThreshold;
            }

            $refillDurationSec = $this->toPositiveInt($diagnosticsTargets['refill_duration_sec'] ?? null);
            if ($refillDurationSec !== null) {
                $executionPatch['refill_duration_sec'] = $refillDurationSec;
            }

            $refillTimeoutSec = $this->toPositiveInt($diagnosticsTargets['refill_timeout_sec'] ?? null);
            if ($refillTimeoutSec !== null) {
                $executionPatch['refill_timeout_sec'] = $refillTimeoutSec;
            }

            if (isset($diagnosticsTargets['refill']) && is_array($diagnosticsTargets['refill'])) {
                $executionPatch['refill'] = $diagnosticsTargets['refill'];
            }

            if (!empty($executionPatch)) {
                $diagnostics = $this->mergeTaskExecution($diagnostics, $executionPatch);
            }
        }

        if ($enabled === false) {
            $diagnostics = $this->mergeTaskExecution($diagnostics, ['force_skip' => true]);
        } elseif ($enabled === true) {
            $diagnostics = $this->mergeTaskExecution($diagnostics, ['force_skip' => false]);
        }

        if (!empty($diagnostics)) {
            $targets['diagnostics'] = $diagnostics;
        }

        return $targets;
    }

    protected function mergeSolutionSubsystem(array $targets, array $subsystems): array
    {
        $solutionSubsystem = null;
        $solutionKey = null;
        $solutionEnabled = null;
        foreach (['solution_change', 'solution'] as $candidate) {
            if (isset($subsystems[$candidate]) && is_array($subsystems[$candidate])) {
                $solutionSubsystem = $subsystems[$candidate];
                $solutionKey = $candidate;
                $solutionEnabled = $this->toBool($solutionSubsystem['enabled'] ?? null);
                break;
            }
        }

        $solutionTargets = is_string($solutionKey)
            ? $this->extractSubsystemTargets($subsystems, $solutionKey)
            : null;
        if ($solutionEnabled === null && !is_array($solutionTargets)) {
            return $targets;
        }

        $solution = is_array($targets['solution_change'] ?? null) ? $targets['solution_change'] : [];
        if (is_array($solutionTargets)) {
            $intervalSec = $this->resolveIntervalSeconds($solutionTargets);
            if ($intervalSec !== null) {
                $solution['interval_sec'] = $intervalSec;
            }

            $durationSec = $this->resolveDurationSeconds($solutionTargets);
            if ($durationSec !== null) {
                $solution['duration_sec'] = $durationSec;
            }

            if (isset($solutionTargets['execution']) && is_array($solutionTargets['execution'])) {
                $solution = $this->mergeTaskExecution($solution, $solutionTargets['execution']);
            }
        }

        if ($solutionEnabled === false) {
            $solution = $this->mergeTaskExecution($solution, ['force_skip' => true]);
        } elseif ($solutionEnabled === true) {
            $solution = $this->mergeTaskExecution($solution, ['force_skip' => false]);
        }

        if (!empty($solution)) {
            $targets['solution_change'] = $solution;
        }

        return $targets;
    }

    protected function appendSubsystemsToExtensions(array $targets, array $subsystems): array
    {
        $extensions = is_array($targets['extensions'] ?? null) ? $targets['extensions'] : [];
        $existingSubsystems = is_array($extensions['subsystems'] ?? null) ? $extensions['subsystems'] : [];
        $extensions['subsystems'] = $this->mergeRecursive($existingSubsystems, $subsystems);
        $targets['extensions'] = $extensions;

        return $targets;
    }

    protected function mergeTaskExecution(array $taskConfig, array $executionPatch): array
    {
        $existingExecution = is_array($taskConfig['execution'] ?? null) ? $taskConfig['execution'] : [];
        $taskConfig['execution'] = $this->mergeRecursive($existingExecution, $executionPatch);
        return $taskConfig;
    }

    protected function extractSubsystemTargets(array $subsystems, string $subsystem): ?array
    {
        $execution = $subsystems[$subsystem]['execution'] ?? null;
        if (!is_array($execution)) {
            return null;
        }

        return array_merge($execution, ['execution' => $execution]);
    }

    protected function extractSubsystemEnabled(array $subsystems, string $subsystem): ?bool
    {
        if (!isset($subsystems[$subsystem]) || !is_array($subsystems[$subsystem])) {
            return null;
        }
        return $this->toBool($subsystems[$subsystem]['enabled'] ?? null);
    }

    protected function resolveIntervalSeconds(array $payload): ?int
    {
        $intervalSec = $this->toPositiveInt($payload['interval_sec'] ?? $payload['every_sec'] ?? null);
        if ($intervalSec !== null) {
            return $intervalSec;
        }

        $intervalMinutes = $this->toPositiveInt($payload['interval_minutes'] ?? null);
        if ($intervalMinutes !== null) {
            return $intervalMinutes * 60;
        }

        return null;
    }

    protected function resolveDurationSeconds(array $payload): ?int
    {
        $durationSec = $this->toPositiveInt($payload['duration_sec'] ?? null);
        if ($durationSec !== null) {
            return $durationSec;
        }

        $durationSeconds = $this->toPositiveInt($payload['duration_seconds'] ?? null);
        if ($durationSeconds !== null) {
            return $durationSeconds;
        }

        return null;
    }

    protected function resolveScheduleStartTime(mixed $rawSchedule): ?string
    {
        if (!is_array($rawSchedule) || empty($rawSchedule)) {
            return null;
        }

        $first = $rawSchedule[0] ?? null;
        if (!is_array($first)) {
            return null;
        }

        return $this->normalizeTimeString($first['start'] ?? null);
    }

    protected function normalizeTimeString(mixed $value): ?string
    {
        if (!is_string($value)) {
            return null;
        }

        $trimmed = trim($value);
        if ($trimmed === '') {
            return null;
        }

        if (preg_match('/^\d{1,2}:\d{2}(:\d{2})?$/', $trimmed) !== 1) {
            return null;
        }

        return $trimmed;
    }

    protected function toPositiveInt(mixed $value): ?int
    {
        if (!is_numeric($value)) {
            return null;
        }

        $result = (int) round((float) $value);
        return $result > 0 ? $result : null;
    }

    protected function toFloat(mixed $value): ?float
    {
        if (!is_numeric($value)) {
            return null;
        }

        return (float) $value;
    }

    protected function toBool(mixed $value): ?bool
    {
        if (is_bool($value)) {
            return $value;
        }

        if (is_numeric($value)) {
            return ((int) $value) === 1;
        }

        if (is_string($value)) {
            $normalized = strtolower(trim($value));
            if (in_array($normalized, ['1', 'true', 'yes', 'on'], true)) {
                return true;
            }
            if (in_array($normalized, ['0', 'false', 'no', 'off'], true)) {
                return false;
            }
        }

        return null;
    }

    protected function mergeRecursive(array $base, array $patch): array
    {
        foreach ($patch as $key => $value) {
            if (is_array($value) && is_array($base[$key] ?? null)) {
                $base[$key] = $this->mergeRecursive($base[$key], $value);
            } else {
                $base[$key] = $value;
            }
        }

        return $base;
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
