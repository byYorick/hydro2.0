<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class GrowCyclePhase extends Model
{
    use HasFactory;

    protected $fillable = [
        'grow_cycle_id',
        'recipe_revision_phase_id',
        'phase_index',
        'name',
        'ph_target',
        'ph_min',
        'ph_max',
        'ec_target',
        'ec_min',
        'ec_max',
        'nutrient_program_code',
        'nutrient_mode',
        'nutrient_npk_ratio_pct',
        'nutrient_calcium_ratio_pct',
        'nutrient_magnesium_ratio_pct',
        'nutrient_micro_ratio_pct',
        'nutrient_npk_dose_ml_l',
        'nutrient_calcium_dose_ml_l',
        'nutrient_magnesium_dose_ml_l',
        'nutrient_micro_dose_ml_l',
        'nutrient_npk_product_id',
        'nutrient_calcium_product_id',
        'nutrient_magnesium_product_id',
        'nutrient_micro_product_id',
        'nutrient_dose_delay_sec',
        'nutrient_ec_stop_tolerance',
        'nutrient_solution_volume_l',
        'irrigation_mode',
        'irrigation_interval_sec',
        'irrigation_duration_sec',
        'lighting_photoperiod_hours',
        'lighting_start_time',
        'mist_interval_sec',
        'mist_duration_sec',
        'mist_mode',
        'temp_air_target',
        'humidity_target',
        'co2_target',
        'progress_model',
        'duration_hours',
        'duration_days',
        'base_temp_c',
        'target_gdd',
        'dli_target',
        'extensions',
        'started_at',
        'ended_at',
    ];

    protected $casts = [
        'ph_target' => 'decimal:2',
        'ph_min' => 'decimal:2',
        'ph_max' => 'decimal:2',
        'ec_target' => 'decimal:2',
        'ec_min' => 'decimal:2',
        'ec_max' => 'decimal:2',
        'nutrient_npk_ratio_pct' => 'decimal:2',
        'nutrient_calcium_ratio_pct' => 'decimal:2',
        'nutrient_magnesium_ratio_pct' => 'decimal:2',
        'nutrient_micro_ratio_pct' => 'decimal:2',
        'nutrient_npk_dose_ml_l' => 'decimal:3',
        'nutrient_calcium_dose_ml_l' => 'decimal:3',
        'nutrient_magnesium_dose_ml_l' => 'decimal:3',
        'nutrient_micro_dose_ml_l' => 'decimal:3',
        'nutrient_ec_stop_tolerance' => 'decimal:3',
        'nutrient_solution_volume_l' => 'decimal:2',
        'temp_air_target' => 'decimal:2',
        'humidity_target' => 'decimal:2',
        'base_temp_c' => 'decimal:2',
        'target_gdd' => 'decimal:2',
        'dli_target' => 'decimal:2',
        'lighting_start_time' => 'datetime',
        'started_at' => 'datetime',
        'ended_at' => 'datetime',
        'extensions' => 'array',
    ];

    /**
     * Цикл выращивания
     */
    public function growCycle(): BelongsTo
    {
        return $this->belongsTo(GrowCycle::class);
    }

    /**
     * Шаблонная фаза ревизии (для трассировки)
     */
    public function recipeRevisionPhase(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhase::class);
    }

    public function npkProduct(): BelongsTo
    {
        return $this->belongsTo(NutrientProduct::class, 'nutrient_npk_product_id');
    }

    public function calciumProduct(): BelongsTo
    {
        return $this->belongsTo(NutrientProduct::class, 'nutrient_calcium_product_id');
    }

    public function magnesiumProduct(): BelongsTo
    {
        return $this->belongsTo(NutrientProduct::class, 'nutrient_magnesium_product_id');
    }

    public function microProduct(): BelongsTo
    {
        return $this->belongsTo(NutrientProduct::class, 'nutrient_micro_product_id');
    }

    /**
     * Шаги этой фазы в цикле
     */
    public function steps(): HasMany
    {
        return $this->hasMany(GrowCyclePhaseStep::class);
    }
}
