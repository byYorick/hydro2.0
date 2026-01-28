<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class InfrastructureAsset extends Model
{
    use HasFactory;

    protected $fillable = [
        'type',
        'name',
        'metadata',
    ];

    protected $casts = [
        'metadata' => 'array',
    ];

    /**
     * Типы оборудования
     */
    public const TYPE_PUMP = 'PUMP';
    public const TYPE_MISTER = 'MISTER';
    public const TYPE_TANK_NUTRIENT = 'TANK_NUTRIENT';
    public const TYPE_TANK_CLEAN = 'TANK_CLEAN';
    public const TYPE_DRAIN = 'DRAIN';
    public const TYPE_LIGHT = 'LIGHT';
    public const TYPE_VENT = 'VENT';
    public const TYPE_HEATER = 'HEATER';

    /**
     * Получить все доступные типы
     */
    public static function getTypes(): array
    {
        return [
            self::TYPE_PUMP,
            self::TYPE_MISTER,
            self::TYPE_TANK_NUTRIENT,
            self::TYPE_TANK_CLEAN,
            self::TYPE_DRAIN,
            self::TYPE_LIGHT,
            self::TYPE_VENT,
            self::TYPE_HEATER,
        ];
    }
}

