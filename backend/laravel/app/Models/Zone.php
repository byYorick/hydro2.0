<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Zone extends Model
{
    use HasFactory;

    protected $fillable = [
        'greenhouse_id',
        'preset_id',
        'name',
        'description',
        'status',
    ];

    public function greenhouse(): BelongsTo
    {
        return $this->belongsTo(Greenhouse::class);
    }

    public function preset(): BelongsTo
    {
        return $this->belongsTo(Preset::class);
    }

    public function nodes(): HasMany
    {
        return $this->hasMany(DeviceNode::class, 'zone_id');
    }

    public function recipeInstance(): HasOne
    {
        return $this->hasOne(ZoneRecipeInstance::class);
    }

    public function alerts(): HasMany
    {
        return $this->hasMany(Alert::class);
    }

    public function predictions(): HasMany
    {
        return $this->hasMany(ParameterPrediction::class);
    }

    public function simulations(): HasMany
    {
        return $this->hasMany(ZoneSimulation::class);
    }

    public function modelParams(): HasMany
    {
        return $this->hasMany(ZoneModelParams::class);
    }
}


