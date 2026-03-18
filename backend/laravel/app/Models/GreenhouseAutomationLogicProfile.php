<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class GreenhouseAutomationLogicProfile extends Model
{
    use HasFactory;

    public const MODE_SETUP = 'setup';

    public const MODE_WORKING = 'working';

    protected $fillable = [
        'greenhouse_id',
        'mode',
        'subsystems',
        'command_plans',
        'is_active',
        'created_by',
        'updated_by',
    ];

    protected $casts = [
        'subsystems' => 'array',
        'command_plans' => 'array',
        'is_active' => 'boolean',
    ];

    /**
     * @return string[]
     */
    public static function allowedModes(): array
    {
        return [self::MODE_SETUP, self::MODE_WORKING];
    }

    public function greenhouse(): BelongsTo
    {
        return $this->belongsTo(Greenhouse::class);
    }

    public function creator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    public function updater(): BelongsTo
    {
        return $this->belongsTo(User::class, 'updated_by');
    }
}
