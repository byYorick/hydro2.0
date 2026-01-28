<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class GrowCyclePhaseStep extends Model
{
    use HasFactory;

    protected $fillable = [
        'grow_cycle_phase_id',
        'recipe_revision_phase_step_id',
        'step_index',
        'name',
        'offset_hours',
        'action',
        'description',
        'ph_target',
        'ph_min',
        'ph_max',
        'ec_target',
        'ec_min',
        'ec_max',
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
        'temp_air_target' => 'decimal:2',
        'humidity_target' => 'decimal:2',
        'lighting_start_time' => 'datetime',
        'started_at' => 'datetime',
        'ended_at' => 'datetime',
        'extensions' => 'array',
    ];

    /**
     * Фаза цикла
     */
    public function growCyclePhase(): BelongsTo
    {
        return $this->belongsTo(GrowCyclePhase::class);
    }

    /**
     * Шаблонный шаг ревизии (для трассировки)
     */
    public function recipeRevisionPhaseStep(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhaseStep::class);
    }
}

