<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasOne;

class ZoneRecipeInstance extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_id',
        'recipe_id',
        'current_phase_index',
        'started_at',
    ];

    protected $casts = [
        'started_at' => 'datetime',
    ];

    protected $appends = ['phase_progress'];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }

    public function growCycle(): HasOne
    {
        return $this->hasOne(GrowCycle::class);
    }

    /**
     * Вычислить прогресс текущей фазы в процентах (0-100)
     */
    public function getPhaseProgressAttribute(): ?float
    {
        if (!$this->started_at) {
            return null;
        }

        $recipe = $this->recipe;
        if (!$recipe) {
            return null;
        }

        // Получаем все фазы рецепта, отсортированные по phase_index
        $phases = $recipe->phases()->orderBy('phase_index')->get();
        if ($phases->isEmpty()) {
            return null;
        }

        // Находим текущую фазу
        $currentPhase = $phases->firstWhere('phase_index', $this->current_phase_index);
        if (!$currentPhase || !$currentPhase->duration_hours) {
            return null;
        }

        // Вычисляем кумулятивное время начала текущей фазы
        $phaseStartCumulative = 0;
        foreach ($phases as $phase) {
            if ($phase->phase_index < $this->current_phase_index) {
                $phaseStartCumulative += $phase->duration_hours ?? 0;
            } else {
                break;
            }
        }

        // Вычисляем прошедшее время с начала рецепта
        $elapsedHours = $this->started_at->diffInHours(now(), false);
        if ($elapsedHours < 0) {
            return 0.0;
        }

        // Вычисляем время в текущей фазе
        $timeInPhaseHours = $elapsedHours - $phaseStartCumulative;
        
        // Если время в фазе отрицательное, значит фаза еще не началась
        if ($timeInPhaseHours < 0) {
            return 0.0;
        }

        // Вычисляем прогресс (0-100%)
        $progress = ($timeInPhaseHours / $currentPhase->duration_hours) * 100.0;
        
        // Ограничиваем от 0 до 100
        return min(100.0, max(0.0, $progress));
    }
}


