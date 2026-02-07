<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class NutrientProduct extends Model
{
    use HasFactory;

    protected $fillable = [
        'manufacturer',
        'name',
        'component',
        'composition',
        'recommended_stage',
        'notes',
        'metadata',
    ];

    protected $casts = [
        'metadata' => 'array',
    ];

    public function recipeRevisionNpkPhases(): HasMany
    {
        return $this->hasMany(RecipeRevisionPhase::class, 'nutrient_npk_product_id');
    }

    public function recipeRevisionCalciumPhases(): HasMany
    {
        return $this->hasMany(RecipeRevisionPhase::class, 'nutrient_calcium_product_id');
    }

    public function recipeRevisionMicroPhases(): HasMany
    {
        return $this->hasMany(RecipeRevisionPhase::class, 'nutrient_micro_product_id');
    }
}
