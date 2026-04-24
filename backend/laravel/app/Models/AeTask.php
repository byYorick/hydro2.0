<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * AE3 task: единица исполнения в automation-engine.
 *
 * В API эта сущность экспортируется как `execution` (`execution_id = ae_tasks.id`).
 * Correction-window живёт внутри task-а как `corr_snapshot_event_id` + `corr_*` поля.
 *
 * @see doc_ai/04_BACKEND_CORE/ae3lite.md
 */
class AeTask extends Model
{
    use HasFactory;

    protected $table = 'ae_tasks';

    protected $fillable = [
        'zone_id',
        'task_type',
        'status',
        'idempotency_key',
        'scheduled_for',
        'due_at',
        'claimed_by',
        'claimed_at',
        'error_code',
        'error_message',
        'completed_at',
        'intent_source',
        'intent_trigger',
        'intent_id',
        'intent_meta',
        'topology',
        'current_stage',
        'workflow_phase',
        'control_mode_snapshot',
        'corr_step',
        'corr_snapshot_event_id',
        'corr_snapshot_created_at',
        'corr_snapshot_cmd_id',
        'corr_snapshot_source_event_type',
        'irrigation_mode',
        'irrigation_requested_duration_sec',
        'irrigation_decision_strategy',
        'irrigation_decision_outcome',
        'irrigation_decision_reason_code',
        'irrigation_decision_degraded',
        'irrigation_decision_config',
        'irrigation_bundle_revision',
        'irrigation_replay_count',
    ];

    protected $casts = [
        'scheduled_for' => 'datetime',
        'due_at' => 'datetime',
        'claimed_at' => 'datetime',
        'completed_at' => 'datetime',
        'corr_snapshot_created_at' => 'datetime',
        'intent_meta' => 'array',
        'irrigation_decision_config' => 'array',
        'irrigation_decision_degraded' => 'boolean',
        'irrigation_replay_count' => 'integer',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function intent(): BelongsTo
    {
        return $this->belongsTo(ZoneAutomationIntent::class, 'intent_id');
    }

    public function snapshotEvent(): BelongsTo
    {
        return $this->belongsTo(ZoneEvent::class, 'corr_snapshot_event_id');
    }

    public function snapshotCommand(): BelongsTo
    {
        return $this->belongsTo(Command::class, 'corr_snapshot_cmd_id', 'cmd_id');
    }
}
