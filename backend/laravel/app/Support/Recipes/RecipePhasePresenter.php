<?php

namespace App\Support\Recipes;

use App\Models\NutrientProduct;
use App\Models\RecipeRevisionPhase;

class RecipePhasePresenter
{
    public function __construct(
        private readonly RecipePhasePayloadNormalizer $normalizer
    ) {}

    /**
     * @return array<string, mixed>
     */
    public function present(RecipeRevisionPhase $phase): array
    {
        $data = $this->normalizer->normalizeForRead($phase);
        $extensions = is_array($data['extensions'] ?? null) ? $data['extensions'] : null;
        $systemType = data_get($extensions, 'subsystems.irrigation.targets.system_type')
            ?? data_get($extensions, 'subsystems.irrigation.execution.system_type');

        return [
            'id' => $phase->id,
            'stage_template_id' => $phase->stage_template_id,
            'stage_template' => $phase->relationLoaded('stageTemplate') && $phase->stageTemplate
                ? [
                    'id' => $phase->stageTemplate->id,
                    'code' => $phase->stageTemplate->code,
                    'name' => $phase->stageTemplate->name,
                ]
                : null,
            'phase_index' => $phase->phase_index,
            'name' => $phase->name,
            'duration_hours' => $phase->duration_hours,
            'duration_days' => $phase->duration_days,
            'ph_target' => $phase->ph_target !== null ? (float) $phase->ph_target : null,
            'ph_min' => $phase->ph_min !== null ? (float) $phase->ph_min : null,
            'ph_max' => $phase->ph_max !== null ? (float) $phase->ph_max : null,
            'ec_target' => $phase->ec_target !== null ? (float) $phase->ec_target : null,
            'ec_min' => $phase->ec_min !== null ? (float) $phase->ec_min : null,
            'ec_max' => $phase->ec_max !== null ? (float) $phase->ec_max : null,
            'temp_air_target' => $phase->temp_air_target !== null ? (float) $phase->temp_air_target : null,
            'humidity_target' => $phase->humidity_target !== null ? (float) $phase->humidity_target : null,
            'lighting_photoperiod_hours' => $phase->lighting_photoperiod_hours,
            'lighting_start_time' => $phase->lighting_start_time?->format('H:i:s'),
            'irrigation_mode' => $phase->irrigation_mode,
            'irrigation_system_type' => $phase->irrigation_system_type ?? (is_string($systemType) ? $systemType : null),
            'substrate_type' => $phase->substrate_type,
            'irrigation_interval_sec' => $phase->irrigation_interval_sec,
            'irrigation_duration_sec' => $phase->irrigation_duration_sec,
            'mist_interval_sec' => $phase->mist_interval_sec,
            'mist_duration_sec' => $phase->mist_duration_sec,
            'mist_mode' => $phase->mist_mode,
            'solution_temp_target' => $phase->solution_temp_target !== null ? (float) $phase->solution_temp_target : null,
            'solution_temp_min' => $phase->solution_temp_min !== null ? (float) $phase->solution_temp_min : null,
            'solution_temp_max' => $phase->solution_temp_max !== null ? (float) $phase->solution_temp_max : null,
            'day_night_enabled' => (bool) $phase->day_night_enabled,
            'nutrient_program_code' => $phase->nutrient_program_code,
            'nutrient_mode' => $phase->nutrient_mode,
            'nutrient_ec_dosing_mode' => $phase->nutrient_ec_dosing_mode,
            'nutrient_npk_ratio_pct' => $phase->nutrient_npk_ratio_pct !== null ? (float) $phase->nutrient_npk_ratio_pct : null,
            'nutrient_calcium_ratio_pct' => $phase->nutrient_calcium_ratio_pct !== null ? (float) $phase->nutrient_calcium_ratio_pct : null,
            'nutrient_magnesium_ratio_pct' => $phase->nutrient_magnesium_ratio_pct !== null ? (float) $phase->nutrient_magnesium_ratio_pct : null,
            'nutrient_micro_ratio_pct' => $phase->nutrient_micro_ratio_pct !== null ? (float) $phase->nutrient_micro_ratio_pct : null,
            'nutrient_npk_dose_ml_l' => $phase->nutrient_npk_dose_ml_l !== null ? (float) $phase->nutrient_npk_dose_ml_l : null,
            'nutrient_calcium_dose_ml_l' => $phase->nutrient_calcium_dose_ml_l !== null ? (float) $phase->nutrient_calcium_dose_ml_l : null,
            'nutrient_magnesium_dose_ml_l' => $phase->nutrient_magnesium_dose_ml_l !== null ? (float) $phase->nutrient_magnesium_dose_ml_l : null,
            'nutrient_micro_dose_ml_l' => $phase->nutrient_micro_dose_ml_l !== null ? (float) $phase->nutrient_micro_dose_ml_l : null,
            'nutrient_npk_product_id' => $phase->nutrient_npk_product_id,
            'nutrient_calcium_product_id' => $phase->nutrient_calcium_product_id,
            'nutrient_magnesium_product_id' => $phase->nutrient_magnesium_product_id,
            'nutrient_micro_product_id' => $phase->nutrient_micro_product_id,
            'npk_product' => $this->presentProduct($phase, 'npkProduct'),
            'calcium_product' => $this->presentProduct($phase, 'calciumProduct'),
            'magnesium_product' => $this->presentProduct($phase, 'magnesiumProduct'),
            'micro_product' => $this->presentProduct($phase, 'microProduct'),
            'nutrient_dose_delay_sec' => $phase->nutrient_dose_delay_sec,
            'nutrient_ec_stop_tolerance' => $phase->nutrient_ec_stop_tolerance !== null ? (float) $phase->nutrient_ec_stop_tolerance : null,
            'nutrient_solution_volume_l' => $phase->nutrient_solution_volume_l !== null ? (float) $phase->nutrient_solution_volume_l : null,
            'progress_model' => $phase->progress_model,
            'phase_advance_strategy' => $phase->phase_advance_strategy,
            'co2_target' => $phase->co2_target,
            'base_temp_c' => $phase->base_temp_c !== null ? (float) $phase->base_temp_c : null,
            'target_gdd' => $phase->target_gdd !== null ? (float) $phase->target_gdd : null,
            'dli_target' => $phase->dli_target !== null ? (float) $phase->dli_target : null,
            'extensions' => $extensions,
            'targets' => [
                'ph' => [
                    'target' => $phase->ph_target !== null ? (float) $phase->ph_target : null,
                    'min' => $phase->ph_min !== null ? (float) $phase->ph_min : ($phase->ph_target !== null ? (float) $phase->ph_target : null),
                    'max' => $phase->ph_max !== null ? (float) $phase->ph_max : ($phase->ph_target !== null ? (float) $phase->ph_target : null),
                ],
                'ec' => [
                    'target' => $phase->ec_target !== null ? (float) $phase->ec_target : null,
                    'min' => $phase->ec_min !== null ? (float) $phase->ec_min : ($phase->ec_target !== null ? (float) $phase->ec_target : null),
                    'max' => $phase->ec_max !== null ? (float) $phase->ec_max : ($phase->ec_target !== null ? (float) $phase->ec_target : null),
                ],
                'temp_air' => $phase->temp_air_target !== null ? (float) $phase->temp_air_target : null,
                'humidity_air' => $phase->humidity_target !== null ? (float) $phase->humidity_target : null,
                'solution_temp' => [
                    'target' => $phase->solution_temp_target !== null ? (float) $phase->solution_temp_target : null,
                    'min' => $phase->solution_temp_min !== null ? (float) $phase->solution_temp_min : null,
                    'max' => $phase->solution_temp_max !== null ? (float) $phase->solution_temp_max : null,
                ],
                'light_hours' => $phase->lighting_photoperiod_hours,
                'irrigation_interval_sec' => $phase->irrigation_interval_sec,
                'irrigation_duration_sec' => $phase->irrigation_duration_sec,
                'irrigation' => [
                    'mode' => $phase->irrigation_mode,
                    'system_type' => $phase->irrigation_system_type ?? (is_string($systemType) ? $systemType : null),
                ],
                'mist' => [
                    'mode' => $phase->mist_mode,
                    'interval_sec' => $phase->mist_interval_sec,
                    'duration_sec' => $phase->mist_duration_sec,
                ],
            ],
        ];
    }

    /**
     * @return array{id: int, manufacturer: string|null, name: string|null, component: string|null}|null
     */
    private function presentProduct(RecipeRevisionPhase $phase, string $relation): ?array
    {
        if (! $phase->relationLoaded($relation)) {
            return null;
        }

        $product = $phase->getRelation($relation);
        if (! $product instanceof NutrientProduct) {
            return null;
        }

        return [
            'id' => $product->id,
            'manufacturer' => $product->manufacturer,
            'name' => $product->name,
            'component' => $product->component,
        ];
    }
}
