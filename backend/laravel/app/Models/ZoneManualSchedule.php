<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneManualSchedule extends Model
{
    protected $fillable = [
        'zone_id',
        'task_type',
        'schedule_kind',
        'time_at',
        'interval_sec',
        'window_start',
        'window_end',
        'days_of_week',
        'run_at',
        'payload',
        'label',
        'enabled',
        'created_by',
    ];

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'payload' => 'array',
            'days_of_week' => 'array',
            'enabled' => 'boolean',
            'interval_sec' => 'integer',
            'run_at' => 'datetime',
            'last_dispatched_at' => 'datetime',
        ];
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function creator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }
}
