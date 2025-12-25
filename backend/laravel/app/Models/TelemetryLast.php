<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TelemetryLast extends Model
{
    use HasFactory;

    protected $table = 'telemetry_last';

    protected $primaryKey = 'sensor_id';

    public $incrementing = false;

    protected $fillable = [
        'sensor_id',
        'last_value',
        'last_ts',
        'last_quality',
    ];

    protected $casts = [
        'last_value' => 'decimal:4',
        'last_ts' => 'datetime',
        'updated_at' => 'datetime',
    ];

    /**
     * Сенсор
     */
    public function sensor(): BelongsTo
    {
        return $this->belongsTo(Sensor::class);
    }
}
