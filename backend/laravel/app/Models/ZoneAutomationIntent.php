<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Intent automation-engine: единица намерения от Laravel scheduler-dispatch
 * перед созданием `ae_task`. `idempotency_key` используется как
 * correlation_id во всём chain.
 */
class ZoneAutomationIntent extends Model
{
    use HasFactory;

    protected $table = 'zone_automation_intents';

    protected $fillable = [
        'zone_id',
        'intent_type',
        'idempotency_key',
        'status',
        'retry_count',
        'max_retries',
        'task_type',
        'topology',
    ];

    protected $casts = [
        'retry_count' => 'integer',
        'max_retries' => 'integer',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function tasks(): HasMany
    {
        return $this->hasMany(AeTask::class, 'intent_id');
    }
}
