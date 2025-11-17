<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ParameterPrediction extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_id',
        'metric_type',
        'predicted_value',
        'confidence',
        'horizon_minutes',
        'predicted_at',
    ];

    protected $casts = [
        'predicted_value' => 'float',
        'confidence' => 'float',
        'horizon_minutes' => 'integer',
        'predicted_at' => 'datetime',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}
