<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Water EC/pH baseline captured at solution_fill for sequential nutrient correction.
 *
 * @see doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md
 */
class ZonePrepareBaseline extends Model
{
    use HasFactory;

    protected $table = 'zone_prepare_baselines';

    protected $fillable = [
        'zone_id',
        'grow_cycle_id',
        'ae_task_id',
        'water_ec',
        'water_ph',
        'target_ec',
        'nutrient_ec_budget',
        'ratios_json',
        'component_targets_json',
        'captured_at',
        'source',
    ];

    protected function casts(): array
    {
        return [
            'water_ec' => 'float',
            'water_ph' => 'float',
            'target_ec' => 'float',
            'nutrient_ec_budget' => 'float',
            'ratios_json' => 'array',
            'component_targets_json' => 'array',
            'captured_at' => 'datetime',
        ];
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function growCycle(): BelongsTo
    {
        return $this->belongsTo(GrowCycle::class);
    }

    public function aeTask(): BelongsTo
    {
        return $this->belongsTo(AeTask::class, 'ae_task_id');
    }
}
