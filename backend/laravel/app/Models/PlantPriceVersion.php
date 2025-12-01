<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class PlantPriceVersion extends Model
{
    use HasFactory;

    protected $fillable = [
        'plant_id',
        'effective_from',
        'effective_to',
        'currency',
        'seedling_cost',
        'substrate_cost',
        'nutrient_cost',
        'labor_cost',
        'protection_cost',
        'logistics_cost',
        'other_cost',
        'wholesale_price',
        'retail_price',
        'source',
        'metadata',
    ];

    protected $casts = [
        'effective_from' => 'date',
        'effective_to' => 'date',
        'seedling_cost' => 'float',
        'substrate_cost' => 'float',
        'nutrient_cost' => 'float',
        'labor_cost' => 'float',
        'protection_cost' => 'float',
        'logistics_cost' => 'float',
        'other_cost' => 'float',
        'wholesale_price' => 'float',
        'retail_price' => 'float',
        'metadata' => 'array',
    ];

    public function plant(): BelongsTo
    {
        return $this->belongsTo(Plant::class);
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
