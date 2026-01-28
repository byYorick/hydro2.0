<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class RecipeRevisionPhaseStep extends Model
{
    use HasFactory;

    protected $fillable = [
        'phase_id',
        'step_index',
        'name',
        'offset_hours',
        'action',
        'description',
        'targets_override',
    ];

    protected $casts = [
        'targets_override' => 'array',
    ];

    /**
     * Фаза, к которой относится этот подшаг
     */
    public function phase(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhase::class, 'phase_id');
    }

    /**
     * Циклы, находящиеся в этом подшаге
     */
    public function growCycles(): HasMany
    {
        return $this->hasMany(GrowCycle::class, 'current_step_id');
    }

    /**
     * Переходы, где этот подшаг является исходным
     */
    public function transitionsFrom(): HasMany
    {
        return $this->hasMany(GrowCycleTransition::class, 'from_step_id');
    }

    /**
     * Переходы, где этот подшаг является целевым
     */
    public function transitionsTo(): HasMany
    {
        return $this->hasMany(GrowCycleTransition::class, 'to_step_id');
    }
}

