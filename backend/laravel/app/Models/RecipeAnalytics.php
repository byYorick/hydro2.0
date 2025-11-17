<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class RecipeAnalytics extends Model
{
    use HasFactory;

    protected $fillable = [
        'recipe_id',
        'zone_id',
        'start_date',
        'end_date',
        'total_duration_hours',
        'avg_ph_deviation',
        'avg_ec_deviation',
        'alerts_count',
        'final_yield',
        'efficiency_score',
        'additional_metrics',
    ];

    protected $casts = [
        'start_date' => 'datetime',
        'end_date' => 'datetime',
        'avg_ph_deviation' => 'decimal:3',
        'avg_ec_deviation' => 'decimal:3',
        'final_yield' => 'array',
        'efficiency_score' => 'decimal:2',
        'additional_metrics' => 'array',
    ];

    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}

