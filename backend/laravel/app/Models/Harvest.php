<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Harvest extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_id',
        'recipe_id',
        'harvest_date',
        'yield_weight_kg',
        'yield_count',
        'quality_score',
        'notes',
    ];

    protected $casts = [
        'harvest_date' => 'date',
        'yield_weight_kg' => 'decimal:2',
        'quality_score' => 'decimal:2',
        'notes' => 'array',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }
}

