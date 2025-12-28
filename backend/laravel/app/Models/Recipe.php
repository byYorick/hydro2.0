<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
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

    /**
     * Растения, с которыми связан рецепт
     */
    public function plants(): BelongsToMany
    {
        return $this
            ->belongsToMany(Plant::class, 'plant_recipe')
            ->withPivot(['season', 'site_type', 'is_default', 'metadata'])
            ->withTimestamps();
    }
}
