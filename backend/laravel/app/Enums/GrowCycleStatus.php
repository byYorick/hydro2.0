<?php

namespace App\Enums;

enum GrowCycleStatus: string
{
    case PLANNED = 'PLANNED';
    case RUNNING = 'RUNNING';
    case PAUSED = 'PAUSED';
    case HARVESTED = 'HARVESTED';
    case ABORTED = 'ABORTED';
    case AWAITING_CONFIRM = 'AWAITING_CONFIRM';

    /**
     * Получить все значения enum как массив строк.
     */
    public static function values(): array
    {
        return array_column(self::cases(), 'value');
    }

    /**
     * Проверить, является ли статус активным (цикл работает).
     */
    public function isActive(): bool
    {
        return in_array($this, [
            self::PLANNED,
            self::RUNNING,
            self::PAUSED,
        ]);
    }

    /**
     * Проверить, является ли статус завершённым.
     */
    public function isCompleted(): bool
    {
        return in_array($this, [
            self::HARVESTED,
            self::ABORTED,
        ]);
    }

    /**
     * Получить человекочитаемое описание статуса.
     */
    public function label(): string
    {
        return match ($this) {
            self::PLANNED => 'Запланирован',
            self::RUNNING => 'Запущен',
            self::PAUSED => 'Приостановлен',
            self::HARVESTED => 'Собран',
            self::ABORTED => 'Прерван',
            self::AWAITING_CONFIRM => 'Ожидает подтверждения',
        };
    }
}

