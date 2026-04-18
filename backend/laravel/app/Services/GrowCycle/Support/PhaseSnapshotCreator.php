<?php

declare(strict_types=1);

namespace App\Services\GrowCycle\Support;

use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\RecipeRevisionPhase;
use Carbon\Carbon;

/**
 * Создаёт snapshot фазы (grow_cycle_phases row) из шаблона (recipe_revision_phases).
 *
 * Snapshot — неизменяемая копия параметров фазы на момент перехода. Используется
 * createCycle, advancePhase, setPhase, changeRecipeRevision. UNIQUE (grow_cycle_id,
 * phase_index) разрешается через max(phase_index)+1 при конфликтах (например, при
 * changeRecipeRevision с новой ревизией, у которой phase_index=0 уже занят).
 */
class PhaseSnapshotCreator
{
    public function create(
        ?GrowCycle $cycle,
        RecipeRevisionPhase $templatePhase,
        ?Carbon $startedAt = null,
    ): GrowCyclePhase {
        $phaseIndex = $this->resolvePhaseIndex($cycle, $templatePhase);

        return GrowCyclePhase::create([
            'grow_cycle_id' => $cycle?->id,
            'recipe_revision_phase_id' => $templatePhase->id,
            'phase_index' => $phaseIndex,
            'name' => $templatePhase->name,
            'ph_target' => $templatePhase->ph_target,
            'ph_min' => $templatePhase->ph_min,
            'ph_max' => $templatePhase->ph_max,
            'ec_target' => $templatePhase->ec_target,
            'ec_min' => $templatePhase->ec_min,
            'ec_max' => $templatePhase->ec_max,
            'nutrient_program_code' => $templatePhase->nutrient_program_code,
            'nutrient_mode' => $templatePhase->nutrient_mode,
            'nutrient_ec_dosing_mode' => $templatePhase->nutrient_ec_dosing_mode,
            'nutrient_npk_ratio_pct' => $templatePhase->nutrient_npk_ratio_pct,
            'nutrient_calcium_ratio_pct' => $templatePhase->nutrient_calcium_ratio_pct,
            'nutrient_magnesium_ratio_pct' => $templatePhase->nutrient_magnesium_ratio_pct,
            'nutrient_micro_ratio_pct' => $templatePhase->nutrient_micro_ratio_pct,
            'nutrient_npk_dose_ml_l' => $templatePhase->nutrient_npk_dose_ml_l,
            'nutrient_calcium_dose_ml_l' => $templatePhase->nutrient_calcium_dose_ml_l,
            'nutrient_magnesium_dose_ml_l' => $templatePhase->nutrient_magnesium_dose_ml_l,
            'nutrient_micro_dose_ml_l' => $templatePhase->nutrient_micro_dose_ml_l,
            'nutrient_npk_product_id' => $templatePhase->nutrient_npk_product_id,
            'nutrient_calcium_product_id' => $templatePhase->nutrient_calcium_product_id,
            'nutrient_magnesium_product_id' => $templatePhase->nutrient_magnesium_product_id,
            'nutrient_micro_product_id' => $templatePhase->nutrient_micro_product_id,
            'nutrient_dose_delay_sec' => $templatePhase->nutrient_dose_delay_sec,
            'nutrient_ec_stop_tolerance' => $templatePhase->nutrient_ec_stop_tolerance,
            'nutrient_solution_volume_l' => $templatePhase->nutrient_solution_volume_l,
            'irrigation_mode' => $templatePhase->irrigation_mode,
            'irrigation_system_type' => $templatePhase->irrigation_system_type,
            'substrate_type' => $templatePhase->substrate_type,
            'day_night_enabled' => $templatePhase->day_night_enabled,
            'irrigation_interval_sec' => $templatePhase->irrigation_interval_sec,
            'irrigation_duration_sec' => $templatePhase->irrigation_duration_sec,
            'lighting_photoperiod_hours' => $templatePhase->lighting_photoperiod_hours,
            'lighting_start_time' => $templatePhase->lighting_start_time,
            'mist_interval_sec' => $templatePhase->mist_interval_sec,
            'mist_duration_sec' => $templatePhase->mist_duration_sec,
            'mist_mode' => $templatePhase->mist_mode,
            'temp_air_target' => $templatePhase->temp_air_target,
            'humidity_target' => $templatePhase->humidity_target,
            'co2_target' => $templatePhase->co2_target,
            'progress_model' => $templatePhase->progress_model,
            'phase_advance_strategy' => $templatePhase->phase_advance_strategy ?? 'time',
            'duration_hours' => $templatePhase->duration_hours,
            'duration_days' => $templatePhase->duration_days,
            'base_temp_c' => $templatePhase->base_temp_c,
            'target_gdd' => $templatePhase->target_gdd,
            'dli_target' => $templatePhase->dli_target,
            'extensions' => $templatePhase->extensions,
            'started_at' => $startedAt,
        ]);
    }

    private function resolvePhaseIndex(?GrowCycle $cycle, RecipeRevisionPhase $templatePhase): int
    {
        $phaseIndex = $templatePhase->phase_index;
        if ($cycle === null) {
            return $phaseIndex;
        }

        $conflict = GrowCyclePhase::query()
            ->where('grow_cycle_id', $cycle->id)
            ->where('phase_index', $phaseIndex)
            ->exists();
        if (! $conflict) {
            return $phaseIndex;
        }

        $maxIndex = (int) GrowCyclePhase::query()
            ->where('grow_cycle_id', $cycle->id)
            ->max('phase_index');

        return $maxIndex + 1;
    }
}
