<?php

namespace App\Enums;

enum NodeLifecycleState: string
{
    case MANUFACTURED = 'MANUFACTURED';
    case UNPROVISIONED = 'UNPROVISIONED';
    case PROVISIONED_WIFI = 'PROVISIONED_WIFI';
    case REGISTERED_BACKEND = 'REGISTERED_BACKEND';
    case ASSIGNED_TO_ZONE = 'ASSIGNED_TO_ZONE';
    case ACTIVE = 'ACTIVE';
    case DEGRADED = 'DEGRADED';
    case MAINTENANCE = 'MAINTENANCE';
    case DECOMMISSIONED = 'DECOMMISSIONED';

    /**
     * Получить все значения enum как массив строк.
     */
    public static function values(): array
    {
        return array_column(self::cases(), 'value');
    }

    /**
     * Проверить, является ли состояние активным (узел работает).
     */
    public function isActive(): bool
    {
        return in_array($this, [
            self::ACTIVE,
            self::DEGRADED,
        ]);
    }

    /**
     * Проверить, является ли состояние неактивным (узел не работает).
     */
    public function isInactive(): bool
    {
        return in_array($this, [
            self::MANUFACTURED,
            self::UNPROVISIONED,
            self::PROVISIONED_WIFI,
            self::MAINTENANCE,
            self::DECOMMISSIONED,
        ]);
    }

    /**
     * Проверить, может ли узел принимать телеметрию в данном состоянии.
     */
    public function canReceiveTelemetry(): bool
    {
        return in_array($this, [
            self::REGISTERED_BACKEND,
            self::ASSIGNED_TO_ZONE,
            self::ACTIVE,
            self::DEGRADED,
        ]);
    }

    /**
     * Проверить, имеет ли узел рабочую конфигурацию WiFi/MQTT.
     * Если узел в одном из этих состояний, значит он уже подключен к WiFi и MQTT.
     * Используется для определения, нужно ли отправлять полную конфигурацию WiFi/MQTT.
     */
    public function hasWorkingConnection(): bool
    {
        return in_array($this, [
            self::REGISTERED_BACKEND,
            self::ASSIGNED_TO_ZONE,
            self::ACTIVE,
            self::DEGRADED,
        ]);
    }

    /**
     * Получить человекочитаемое описание состояния.
     */
    public function label(): string
    {
        return match ($this) {
            self::MANUFACTURED => 'Произведён',
            self::UNPROVISIONED => 'Не настроен',
            self::PROVISIONED_WIFI => 'Wi-Fi настроен',
            self::REGISTERED_BACKEND => 'Зарегистрирован',
            self::ASSIGNED_TO_ZONE => 'Привязан к зоне',
            self::ACTIVE => 'Активен',
            self::DEGRADED => 'С проблемами',
            self::MAINTENANCE => 'Обслуживание',
            self::DECOMMISSIONED => 'Списан',
        };
    }
}
