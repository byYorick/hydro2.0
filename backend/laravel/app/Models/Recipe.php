<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Recipe extends Model
{
    use HasFactory;

    protected $fillable = [
        'name',
        'description',
        'metadata',
    ];

    protected $casts = [
        'metadata' => 'array',
    ];

    /**
     * Ревизии рецепта
     */
    public function revisions(): HasMany
    {
        return $this->hasMany(RecipeRevision::class)->orderBy('revision_number');
    }

    /**
     * Опубликованные ревизии
     */
    public function publishedRevisions(): HasMany
    {
        return $this->hasMany(RecipeRevision::class)
            ->where('status', 'PUBLISHED')
            ->orderBy('revision_number');
    }

    /**
     * Черновики ревизий
     */
    public function draftRevisions(): HasMany
    {
        return $this->hasMany(RecipeRevision::class)
            ->where('status', 'DRAFT')
            ->orderBy('revision_number');
    }

    /**
     * Последняя опубликованная ревизия
     */
    public function latestPublishedRevision()
    {
        return $this->hasOne(RecipeRevision::class)
            ->where('status', 'PUBLISHED')
            ->orderBy('revision_number', 'desc');
    }

    /**
     * Последний черновик
     */
    public function latestDraftRevision()
    {
        return $this->hasOne(RecipeRevision::class)
            ->where('status', 'DRAFT')
            ->orderBy('revision_number', 'desc');
    }

    // Legacy методы (deprecated, будут удалены после полного перехода)
    /**
     * @deprecated Используйте revisions() вместо phases()
     */
    public function phases(): HasMany
    {
        return $this->hasMany(RecipePhase::class);
    }

    /**
     * @deprecated Используйте growCycles через revisions
     */
    public function zoneRecipeInstances(): HasMany
    {
        return $this->hasMany(\App\Models\ZoneRecipeInstance::class);
    }

    /**
     * @deprecated Используйте stage_template_id в recipe_revision_phases
     */
    public function stageMaps(): HasMany
    {
        return $this->hasMany(RecipeStageMap::class)->orderBy('order_index');
    }
}


