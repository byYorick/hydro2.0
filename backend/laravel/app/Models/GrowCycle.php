<?php

namespace App\Models;

use App\Enums\GrowCycleStatus;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class GrowCycle extends Model
{
    use HasFactory;

    protected $fillable = [
        'greenhouse_id',
        'zone_id',
        'plant_id',
        'recipe_id', // Оставлено для совместимости, но основной источник - recipe_revision_id
        'recipe_revision_id',
        'current_phase_id',
        'current_step_id',
        'status',
        'started_at',
        'recipe_started_at',
        'expected_harvest_at',
        'actual_harvest_at',
        'batch_label',
        'notes',
        'settings',
        'planting_at',
        'phase_started_at',
        'step_started_at',
        'progress_meta',
    ];

    protected $casts = [
        'status' => GrowCycleStatus::class,
        'started_at' => 'datetime',
        'recipe_started_at' => 'datetime',
        'expected_harvest_at' => 'datetime',
        'actual_harvest_at' => 'datetime',
        'planting_at' => 'datetime',
        'phase_started_at' => 'datetime',
        'step_started_at' => 'datetime',
        'settings' => 'array',
        'progress_meta' => 'array',
    ];

    public function greenhouse(): BelongsTo
    {
        return $this->belongsTo(Greenhouse::class);
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function plant(): BelongsTo
    {
        return $this->belongsTo(Plant::class);
    }

    /**
     * Рецепт (legacy, для совместимости)
     * Основной источник - recipeRevision()
     */
    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }

    /**
     * Ревизия рецепта (центр истины)
     */
    public function recipeRevision(): BelongsTo
    {
        return $this->belongsTo(RecipeRevision::class);
    }

    /**
     * Текущая фаза цикла
     */
    public function currentPhase(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhase::class, 'current_phase_id');
    }

    /**
     * Текущий подшаг цикла
     */
    public function currentStep(): BelongsTo
    {
        return $this->belongsTo(RecipeRevisionPhaseStep::class, 'current_step_id');
    }

    /**
     * Перекрытия целевых параметров
     */
    public function overrides(): HasMany
    {
        return $this->hasMany(GrowCycleOverride::class);
    }

    /**
     * Активные перекрытия
     */
    public function activeOverrides(): HasMany
    {
        return $this->hasMany(GrowCycleOverride::class)
            ->where('is_active', true);
    }

    /**
     * История переходов фаз
     */
    public function transitions(): HasMany
    {
        return $this->hasMany(GrowCycleTransition::class)->orderBy('created_at');
    }

    /**
     * Проверка, является ли цикл активным (RUNNING или PAUSED)
     */
    public function isActive(): bool
    {
        return in_array($this->status, [GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED]);
    }

    /**
     * Scope для активных циклов
     */
    public function scopeActive($query)
    {
        return $query->whereIn('status', [GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED]);
    }

    /**
     * Scope для циклов в зоне
     */
    public function scopeForZone($query, int $zoneId)
    {
        return $query->where('zone_id', $zoneId);
    }
}

