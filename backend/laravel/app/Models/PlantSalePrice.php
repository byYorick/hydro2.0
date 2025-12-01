<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class PlantSalePrice extends Model
{
    use HasFactory;

    protected $fillable = [
        'plant_id',
        'plant_price_version_id',
        'channel',
        'price',
        'currency',
        'is_active',
        'metadata',
    ];

    protected $casts = [
        'price' => 'float',
        'is_active' => 'boolean',
        'metadata' => 'array',
    ];

    public function plant(): BelongsTo
    {
        return $this->belongsTo(Plant::class);
    }

    public function priceVersion(): BelongsTo
    {
        return $this->belongsTo(PlantPriceVersion::class, 'plant_price_version_id');
    }
}
