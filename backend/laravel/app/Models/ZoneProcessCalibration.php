<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneProcessCalibration extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_id',
        'mode',
        'ec_gain_per_ml',
        'ph_up_gain_per_ml',
        'ph_down_gain_per_ml',
        'ph_per_ec_ml',
        'ec_per_ph_ml',
        'transport_delay_sec',
        'settle_sec',
        'confidence',
        'source',
        'valid_from',
        'valid_to',
        'is_active',
        'meta',
    ];

    protected $casts = [
        'ec_gain_per_ml' => 'float',
        'ph_up_gain_per_ml' => 'float',
        'ph_down_gain_per_ml' => 'float',
        'ph_per_ec_ml' => 'float',
        'ec_per_ph_ml' => 'float',
        'transport_delay_sec' => 'integer',
        'settle_sec' => 'integer',
        'confidence' => 'float',
        'valid_from' => 'datetime',
        'valid_to' => 'datetime',
        'is_active' => 'boolean',
        'meta' => 'array',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}
