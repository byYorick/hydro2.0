<?php

namespace App\Services;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class Ae3ZoneLeaseGuard
{
    /**
     * @var list<string>
     */
    public const OPERATOR_DEVICE_COMMANDS = [
        'FORCE_PH_CONTROL',
        'FORCE_EC_CONTROL',
        'FORCE_LIGHTING',
        'FORCE_CLIMATE',
    ];

    /**
     * @var list<string>
     */
    private const READ_ONLY_NODE_COMMANDS = [
        'state',
        'test_sensor',
    ];

    public function isHeld(int $zoneId): bool
    {
        if ($zoneId <= 0 || ! Schema::hasTable('ae_zone_leases')) {
            return false;
        }

        return DB::table('ae_zone_leases')
            ->where('zone_id', $zoneId)
            ->where('leased_until', '>', now())
            ->exists();
    }

    public function shouldBlockOperatorZoneCommand(string $type): bool
    {
        return in_array($type, self::OPERATOR_DEVICE_COMMANDS, true);
    }

    /**
     * @param  array<string, mixed>  $params
     */
    public function shouldBlockOperatorNodeCommand(string $cmd, array $params = []): bool
    {
        $name = strtolower(trim($cmd));
        if ($name === '' || in_array($name, self::READ_ONLY_NODE_COMMANDS, true)) {
            return false;
        }

        if ($this->isFailSafeOff($name, $params)) {
            return false;
        }

        return true;
    }

    /**
     * @param  array<string, mixed>  $params
     */
    private function isFailSafeOff(string $cmd, array $params): bool
    {
        if (in_array($cmd, ['set_relay', 'set_state'], true)) {
            $state = $params['state'] ?? null;
            if (is_string($state)) {
                return in_array(strtolower(trim($state)), ['0', 'false', 'off', 'no'], true);
            }

            return $state === false || $state === 0;
        }

        if ($cmd === 'set_pwm') {
            $duty = $params['duty'] ?? ($params['duty_pct'] ?? ($params['percent'] ?? null));

            return is_numeric($duty) && (float) $duty <= 0;
        }

        return false;
    }
}
