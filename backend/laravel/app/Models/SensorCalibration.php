<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class SensorCalibration extends Model
{
    use HasFactory;

    public const STATUS_STARTED = 'started';
    public const STATUS_POINT_1_PENDING = 'point_1_pending';
    public const STATUS_POINT_1_DONE = 'point_1_done';
    public const STATUS_POINT_2_PENDING = 'point_2_pending';
    public const STATUS_COMPLETED = 'completed';
    public const STATUS_FAILED = 'failed';
    public const STATUS_CANCELLED = 'cancelled';

    public const TERMINAL_STATUSES = [
        self::STATUS_COMPLETED,
        self::STATUS_FAILED,
        self::STATUS_CANCELLED,
    ];

    protected $fillable = [
        'zone_id',
        'node_channel_id',
        'sensor_type',
        'status',
        'point_1_reference',
        'point_1_command_id',
        'point_1_sent_at',
        'point_1_result',
        'point_1_error',
        'point_2_reference',
        'point_2_command_id',
        'point_2_sent_at',
        'point_2_result',
        'point_2_error',
        'completed_at',
        'calibrated_by',
        'notes',
        'meta',
    ];

    protected $casts = [
        'point_1_reference' => 'float',
        'point_2_reference' => 'float',
        'point_1_sent_at' => 'datetime',
        'point_2_sent_at' => 'datetime',
        'completed_at' => 'datetime',
        'meta' => 'array',
    ];

    public function isTerminal(): bool
    {
        return in_array($this->status, self::TERMINAL_STATUSES, true);
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function nodeChannel(): BelongsTo
    {
        return $this->belongsTo(NodeChannel::class);
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class, 'calibrated_by');
    }
}
