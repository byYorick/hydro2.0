<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneModelParams extends Model
{
    use HasFactory;

    protected $table = 'zone_model_params';

    protected $fillable = [
        'zone_id',
        'model_type',
        'params',
        'calibrated_at',
    ];

    protected $casts = [
        'params' => 'array',
        'calibrated_at' => 'datetime',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}
