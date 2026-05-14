<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class GreenhouseAutomationState extends Model
{
    public $timestamps = true;

    protected $table = 'greenhouse_automation_state';

    protected $primaryKey = 'greenhouse_id';

    public $incrementing = false;

    protected $keyType = 'int';

    protected $fillable = [
        'greenhouse_id',
        'climate_enabled',
        'control_mode',
        'next_scheduled_tick_at',
        'left_position_pct',
        'right_position_pct',
        'recommended_left_position_pct',
        'recommended_right_position_pct',
        'last_sent_left_position_pct',
        'last_sent_right_position_pct',
        'decision_reason',
        'decision_factors',
        'weather_fresh',
        'inside_climate_fresh',
        'active_manual_override_id',
        'last_task_id',
        'last_error_code',
        'last_error_message',
        'active_alerts_summary',
        'last_decision_at',
        'last_command_at',
        'last_left_cmd_id',
        'last_right_cmd_id',
    ];

    protected function casts(): array
    {
        return [
            'climate_enabled' => 'boolean',
            'weather_fresh' => 'boolean',
            'inside_climate_fresh' => 'boolean',
            'decision_factors' => 'array',
            'active_alerts_summary' => 'array',
            'active_manual_override_id' => 'integer',
            'last_task_id' => 'integer',
            'next_scheduled_tick_at' => 'datetime',
            'last_decision_at' => 'datetime',
            'last_command_at' => 'datetime',
        ];
    }

    public function greenhouse(): BelongsTo
    {
        return $this->belongsTo(Greenhouse::class);
    }
}
