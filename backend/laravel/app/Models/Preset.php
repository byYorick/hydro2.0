<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Preset extends Model
{
    use HasFactory;

    protected $fillable = [
        'name',
        'plant_type',
        'ph_optimal_range',
        'ec_range',
        'vpd_range',
        'light_intensity_range',
        'climate_ranges',
        'irrigation_behavior',
        'growth_profile',
        'default_recipe_id',
        'description',
    ];

    protected $casts = [
        'ph_optimal_range' => 'array',
        'ec_range' => 'array',
        'vpd_range' => 'array',
        'light_intensity_range' => 'array',
        'climate_ranges' => 'array',
        'irrigation_behavior' => 'array',
    ];

    public function defaultRecipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class, 'default_recipe_id');
    }

    public function zones(): HasMany
    {
        return $this->hasMany(Zone::class);
    }
}

