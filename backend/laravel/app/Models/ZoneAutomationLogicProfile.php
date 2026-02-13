<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneAutomationLogicProfile extends Model
{
    use HasFactory;

    public const MODE_SETUP = 'setup';

    public const MODE_WORKING = 'working';

    protected $fillable = [
        'zone_id',
        'mode',
        'subsystems',
        'is_active',
        'created_by',
        'updated_by',
    ];

    protected $casts = [
        'subsystems' => 'array',
        'is_active' => 'boolean',
    ];

    /**
     * @return string[]
     */
    public static function allowedModes(): array
    {
        return [self::MODE_SETUP, self::MODE_WORKING];
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
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
