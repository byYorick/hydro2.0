<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Plant extends Model
{
    use HasFactory;

    protected $fillable = [
        'slug',
        'name',
        'species',
        'variety',
        'substrate_type',
        'growing_system',
        'photoperiod_preset',
        'seasonality',
        'icon_path',
        'description',
        'environment_requirements',
        'growth_phases',
        'recommended_recipes',
        'metadata',
    ];

    protected $casts = [
        'environment_requirements' => 'array',
        'growth_phases' => 'array',
        'recommended_recipes' => 'array',
        'metadata' => 'array',
    ];

    public function zones(): BelongsToMany
    {
        return $this
            ->belongsToMany(Zone::class, 'plant_zone')
            ->withPivot(['assigned_at', 'metadata'])
            ->withTimestamps();
    }

    public function recipes(): BelongsToMany
    {
        return $this
            ->belongsToMany(Recipe::class, 'plant_recipe')
            ->withPivot(['season', 'site_type', 'is_default', 'metadata'])
            ->withTimestamps();
    }

    public function cycles(): HasMany
    {
        return $this->hasMany(PlantCycle::class);
    }

    public function priceVersions(): HasMany
    {
        return $this->hasMany(PlantPriceVersion::class);
    }

    public function costItems(): HasMany
    {
        return $this->hasMany(PlantCostItem::class);
    }

    public function salePrices(): HasMany
    {
        return $this->hasMany(PlantSalePrice::class);
    }
}
