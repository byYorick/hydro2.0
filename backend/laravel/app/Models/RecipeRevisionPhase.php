<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class RecipeRevisionPhase extends Model
{
    use HasFactory;

    protected $appends = [
        'targets',
    ];

    protected $fillable = [
        'recipe_revision_id',
        'stage_template_id',
        'phase_index',
        'name',
        // Обязательные параметры (MVP)
        'ph_target',
        'ph_min',
        'ph_max',
        'ec_target',
        'ec_min',
        'ec_max',
        'nutrient_program_code',
        'nutrient_npk_ratio_pct',
        'nutrient_calcium_ratio_pct',
        'nutrient_micro_ratio_pct',
        'nutrient_npk_dose_ml_l',
        'nutrient_calcium_dose_ml_l',
        'nutrient_micro_dose_ml_l',
        'nutrient_npk_product_id',
        'nutrient_calcium_product_id',
        'nutrient_micro_product_id',
        'nutrient_dose_delay_sec',
        'nutrient_ec_stop_tolerance',
        'irrigation_mode',
        'irrigation_interval_sec',
        'irrigation_duration_sec',
        // Опциональные параметры
        'lighting_photoperiod_hours',
        'lighting_start_time',
        'mist_interval_sec',
        'mist_duration_sec',
        'mist_mode',
        'temp_air_target',
        'humidity_target',
        'co2_target',
        // Прогресс фазы
        'progress_model',
        'duration_hours',
        'duration_days',
        'base_temp_c',
        'target_gdd',
        'dli_target',
        'extensions',
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
        'nutrient_micro_ratio_pct' => 'decimal:2',
        'nutrient_npk_dose_ml_l' => 'decimal:3',
        'nutrient_calcium_dose_ml_l' => 'decimal:3',
        'nutrient_micro_dose_ml_l' => 'decimal:3',
        'nutrient_ec_stop_tolerance' => 'decimal:3',
        'temp_air_target' => 'decimal:2',
        'humidity_target' => 'decimal:2',
        'base_temp_c' => 'decimal:2',
        'target_gdd' => 'decimal:2',
        'dli_target' => 'decimal:2',
        'lighting_start_time' => 'datetime',
        'extensions' => 'array',
    ];

    /**
     * Ревизия рецепта, к которой относится эта фаза
     */
    public function recipeRevision(): BelongsTo
    {
        return $this->belongsTo(RecipeRevision::class);
    }

    /**
     * Шаблон стадии для UI отображения
     */
    public function stageTemplate(): BelongsTo
    {
        return $this->belongsTo(GrowStageTemplate::class);
    }

    public function npkProduct(): BelongsTo
    {
        return $this->belongsTo(NutrientProduct::class, 'nutrient_npk_product_id');
    }

    public function calciumProduct(): BelongsTo
    {
        return $this->belongsTo(NutrientProduct::class, 'nutrient_calcium_product_id');
    }

    public function microProduct(): BelongsTo
    {
        return $this->belongsTo(NutrientProduct::class, 'nutrient_micro_product_id');
    }

    /**
     * Подшаги внутри этой фазы
     */
    public function steps(): HasMany
    {
        return $this->hasMany(RecipeRevisionPhaseStep::class, 'phase_id')->orderBy('step_index');
    }

    /**
     * Циклы, находящиеся в этой фазе
     */
    public function growCycles(): HasMany
    {
        return $this->hasMany(GrowCycle::class, 'current_phase_id');
    }

    /**
     * Переходы, где эта фаза является исходной
     */
    public function transitionsFrom(): HasMany
    {
        return $this->hasMany(GrowCycleTransition::class, 'from_phase_id');
    }

    /**
     * Переходы, где эта фаза является целевой
     */
    public function transitionsTo(): HasMany
    {
        return $this->hasMany(GrowCycleTransition::class, 'to_phase_id');
    }

    /**
     * Сформировать совместимые targets для фронтенда (legacy-формат)
     */
    public function getTargetsAttribute(): array
    {
        $targets = [];

        $phMin = $this->ph_min ?? $this->ph_target;
        $phMax = $this->ph_max ?? $this->ph_target;
        if ($phMin !== null || $phMax !== null) {
            $targets['ph'] = [
                'min' => $phMin,
                'max' => $phMax,
            ];
        }

        $ecMin = $this->ec_min ?? $this->ec_target;
        $ecMax = $this->ec_max ?? $this->ec_target;
        if ($ecMin !== null || $ecMax !== null) {
            $targets['ec'] = [
                'min' => $ecMin,
                'max' => $ecMax,
            ];
        }

        return $targets;
    }
}
