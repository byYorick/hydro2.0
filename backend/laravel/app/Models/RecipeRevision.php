<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class RecipeRevision extends Model
{
    use HasFactory;

    protected $fillable = [
        'recipe_id',
        'revision_number',
        'status',
        'description',
        'created_by',
        'published_at',
    ];

    protected $casts = [
        'published_at' => 'datetime',
    ];

    /**
     * Рецепт, к которому относится эта ревизия
     */
    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }

    /**
     * Пользователь, создавший ревизию
     */
    public function creator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    /**
     * Фазы этой ревизии
     */
    public function phases(): HasMany
    {
        return $this->hasMany(RecipeRevisionPhase::class)->orderBy('phase_index');
    }

    /**
     * Циклы, использующие эту ревизию
     */
    public function growCycles(): HasMany
    {
        return $this->hasMany(GrowCycle::class);
    }

    /**
     * Проверка, является ли ревизия опубликованной
     */
    public function isPublished(): bool
    {
        return $this->status === 'PUBLISHED';
    }

    /**
     * Проверка, является ли ревизия черновиком
     */
    public function isDraft(): bool
    {
        return $this->status === 'DRAFT';
    }
}

