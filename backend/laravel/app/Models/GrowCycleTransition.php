<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class GrowCycleTransition extends Model
{
    use HasFactory;

    protected $fillable = [
        'grow_cycle_id',
        'from_phase_id',
        'to_phase_id',
        'from_step_id',
        'to_step_id',
        'trigger',
        'comment',
        'triggered_by',
        'metadata',
    ];

    protected $casts = [
        'metadata' => 'array',
    ];

    /**
     * Цикл выращивания, в котором произошел переход
     */
    public function growCycle(): BelongsTo
    {
        return $this->belongsTo(GrowCycle::class);
    }

    /**
     * Исходная фаза
     */
    public function fromPhase(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhase::class, 'from_phase_id');
    }

    /**
     * Целевая фаза
     */
    public function toPhase(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhase::class, 'to_phase_id');
    }

    /**
     * Исходный подшаг
     */
    public function fromStep(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhaseStep::class, 'from_step_id');
    }

    /**
     * Целевой подшаг
     */
    public function toStep(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhaseStep::class, 'to_step_id');
    }

    /**
     * Пользователь, инициировавший переход
     */
    public function triggerer(): BelongsTo
    {
        return $this->belongsTo(User::class, 'triggered_by');
    }
}

