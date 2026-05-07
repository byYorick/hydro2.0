<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\NodeChannel;
use DomainException;

/**
 * Имена каналов в MQTT/команде calibrate должны совпадать с прошивкой ph_node / ec_node
 * (см. doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md).
 */
final class SensorCalibrationFirmwareChannel
{
    public const PH = 'ph_sensor';

    public const EC = 'ec_sensor';

    public static function canonicalForSensorType(string $sensorType): string
    {
        return match ($sensorType) {
            'ph' => self::PH,
            'ec' => self::EC,
            default => throw new DomainException('Unsupported sensor_type for firmware calibration.'),
        };
    }

    public static function channelUid(NodeChannel $channel): string
    {
        return strtolower(trim((string) $channel->channel));
    }

    public static function matchesFirmware(NodeChannel $channel, string $sensorType): bool
    {
        return self::channelUid($channel) === self::canonicalForSensorType($sensorType);
    }

    /** @throws DomainException */
    public static function assertMatchesFirmware(NodeChannel $channel, string $sensorType): void
    {
        $expected = self::canonicalForSensorType($sensorType);
        $actual = self::channelUid($channel);
        if ($actual === $expected) {
            return;
        }

        throw new DomainException(
            "node channel uid must be \"{$expected}\" for {$sensorType} calibration (firmware contract); got \"{$channel->channel}\". "
            .'Rename the channel in node configuration to match NODE_CHANNELS_REFERENCE.',
        );
    }
}
