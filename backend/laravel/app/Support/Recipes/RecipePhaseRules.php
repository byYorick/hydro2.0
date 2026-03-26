<?php

namespace App\Support\Recipes;

class RecipePhaseRules
{
    /**
     * @return array<string, array<int, string>>
     */
    public static function store(string $prefix = ''): array
    {
        return self::build($prefix, false);
    }

    /**
     * @return array<string, array<int, string>>
     */
    public static function update(string $prefix = ''): array
    {
        return self::build($prefix, true);
    }

    /**
     * @return array<string, array<int, string>>
     */
    private static function build(string $prefix, bool $partial): array
    {
        $nameRules = $partial
            ? ['sometimes', 'required', 'string', 'max:255']
            : ['required', 'string', 'max:255'];
        $targetRules = $partial
            ? ['sometimes', 'nullable', 'numeric']
            : ['required', 'numeric'];
        $phBoundRules = $partial
            ? ['sometimes', 'nullable', 'numeric', 'min:0', 'max:14']
            : ['required', 'numeric', 'min:0', 'max:14'];
        $ecBoundRules = $partial
            ? ['sometimes', 'nullable', 'numeric', 'min:0']
            : ['required', 'numeric', 'min:0'];

        return [
            $prefix.'stage_template_id' => ['nullable', 'integer', 'exists:grow_stage_templates,id'],
            $prefix.'phase_index' => ['nullable', 'integer', 'min:0'],
            $prefix.'name' => $nameRules,
            $prefix.'ph_target' => [...$targetRules, 'min:0', 'max:14'],
            $prefix.'ph_min' => $phBoundRules,
            $prefix.'ph_max' => $phBoundRules,
            $prefix.'ec_target' => [...$targetRules, 'min:0'],
            $prefix.'ec_min' => $ecBoundRules,
            $prefix.'ec_max' => $ecBoundRules,
            $prefix.'nutrient_program_code' => ['nullable', 'string', 'max:64'],
            $prefix.'nutrient_mode' => ['nullable', 'string', 'in:ratio_ec_pid,delta_ec_by_k,dose_ml_l_only'],
            $prefix.'nutrient_npk_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            $prefix.'nutrient_calcium_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            $prefix.'nutrient_magnesium_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            $prefix.'nutrient_micro_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            $prefix.'nutrient_npk_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            $prefix.'nutrient_calcium_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            $prefix.'nutrient_magnesium_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            $prefix.'nutrient_micro_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            $prefix.'nutrient_npk_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            $prefix.'nutrient_calcium_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            $prefix.'nutrient_magnesium_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            $prefix.'nutrient_micro_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            $prefix.'nutrient_dose_delay_sec' => ['nullable', 'integer', 'min:0', 'max:3600'],
            $prefix.'nutrient_ec_stop_tolerance' => ['nullable', 'numeric', 'min:0', 'max:5'],
            $prefix.'nutrient_solution_volume_l' => ['nullable', 'numeric', 'min:0.1', 'max:100000'],
            $prefix.'irrigation_mode' => ['nullable', 'string', 'in:SUBSTRATE,RECIRC'],
            $prefix.'irrigation_interval_sec' => ['nullable', 'integer', 'min:0'],
            $prefix.'irrigation_duration_sec' => ['nullable', 'integer', 'min:0'],
            $prefix.'lighting_photoperiod_hours' => ['nullable', 'integer', 'min:0', 'max:24'],
            $prefix.'lighting_start_time' => ['nullable', 'date_format:H:i:s'],
            $prefix.'mist_interval_sec' => ['nullable', 'integer', 'min:0'],
            $prefix.'mist_duration_sec' => ['nullable', 'integer', 'min:0'],
            $prefix.'mist_mode' => ['nullable', 'string', 'in:NORMAL,SPRAY'],
            $prefix.'temp_air_target' => ['nullable', 'numeric'],
            $prefix.'humidity_target' => ['nullable', 'numeric', 'min:0', 'max:100'],
            $prefix.'co2_target' => ['nullable', 'integer', 'min:0'],
            $prefix.'progress_model' => ['nullable', 'string', 'in:TIME,TIME_WITH_TEMP_CORRECTION,GDD,DLI'],
            $prefix.'duration_hours' => ['nullable', 'integer', 'min:0'],
            $prefix.'duration_days' => ['nullable', 'integer', 'min:0'],
            $prefix.'base_temp_c' => ['nullable', 'numeric'],
            $prefix.'target_gdd' => ['nullable', 'numeric', 'min:0'],
            $prefix.'dli_target' => ['nullable', 'numeric', 'min:0'],
            $prefix.'extensions' => ['nullable', 'array'],
        ];
    }
}
