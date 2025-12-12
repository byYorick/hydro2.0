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

    public function phases(): HasMany
    {
        return $this->hasMany(RecipePhase::class);
    }

    public function zoneRecipeInstances(): HasMany
    {
        return $this->hasMany(\App\Models\ZoneRecipeInstance::class);
    }

    public function stageMaps(): HasMany
    {
        return $this->hasMany(RecipeStageMap::class)->orderBy('order_index');
    }
}


