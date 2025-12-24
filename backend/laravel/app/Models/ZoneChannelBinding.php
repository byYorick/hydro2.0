<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneChannelBinding extends Model
{
    use HasFactory;

    protected $table = 'zone_channel_bindings';

    protected $fillable = [
        'zone_id',
        'asset_id',
        'node_id',
        'channel',
        'direction',
        'role',
    ];

    /**
     * Связь с зоной
     */
    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    /**
     * Связь с оборудованием зоны
     */
    public function asset(): BelongsTo
    {
        return $this->belongsTo(ZoneInfrastructure::class, 'asset_id');
    }

    /**
     * Связь с нодой
     */
    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
    }

    /**
     * Направления
     */
    public const DIRECTION_ACTUATOR = 'actuator';
    public const DIRECTION_SENSOR = 'sensor';

    /**
     * Роли оборудования
     */
    public const ROLE_MAIN_PUMP = 'main_pump';
    public const ROLE_DRAIN_PUMP = 'drain_pump';
    public const ROLE_MISTER = 'mister';
    public const ROLE_FAN = 'fan';
    public const ROLE_HEATER = 'heater';
    public const ROLE_LIGHT = 'light';
    public const ROLE_VENT = 'vent';
    public const ROLE_PH_SENSOR = 'ph_sensor';
    public const ROLE_EC_SENSOR = 'ec_sensor';
    public const ROLE_TEMP_SENSOR = 'temp_sensor';
    public const ROLE_FLOW_SENSOR = 'flow_sensor';

    /**
     * Получить все доступные роли
     */
    public static function getRoles(): array
    {
        return [
            self::ROLE_MAIN_PUMP,
            self::ROLE_DRAIN_PUMP,
            self::ROLE_MISTER,
            self::ROLE_FAN,
            self::ROLE_HEATER,
            self::ROLE_LIGHT,
            self::ROLE_VENT,
            self::ROLE_PH_SENSOR,
            self::ROLE_EC_SENSOR,
            self::ROLE_TEMP_SENSOR,
            self::ROLE_FLOW_SENSOR,
        ];
    }
}

