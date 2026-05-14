<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class GreenhouseAutomationIntent extends Model
{
    public $timestamps = true;

    protected $table = 'greenhouse_automation_intents';

    protected $fillable = [
        'greenhouse_id',
        'intent_type',
        'task_type',
        'intent_source',
        'idempotency_key',
        'status',
        'not_before',
        'claimed_at',
        'completed_at',
        'error_code',
        'error_message',
        'retry_count',
        'max_retries',
    ];

    protected function casts(): array
    {
        return [
            'not_before' => 'datetime',
            'claimed_at' => 'datetime',
            'completed_at' => 'datetime',
        ];
    }

    public function greenhouse(): BelongsTo
    {
        return $this->belongsTo(Greenhouse::class);
    }
}
