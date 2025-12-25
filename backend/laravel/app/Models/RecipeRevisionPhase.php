<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class RecipeRevisionPhase extends Model
{
    use HasFactory;

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

    /**
     * Подшаги внутри этой фазы
     */
    public function steps(): HasMany
    {
        return $this->hasMany(RecipeRevisionPhaseStep::class)->orderBy('step_index');
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
}

