<?php

namespace App\Support;

final class PumpCalibrationCatalog
{
    public const DOSING_ROLES = [
        'pump_acid',
        'pump_base',
        'pump_a',
        'pump_b',
        'pump_c',
        'pump_d',
    ];

    public const ROLE_COMPONENT_MAP = [
        'pump_acid' => 'ph_down',
        'pump_base' => 'ph_up',
        'pump_a' => 'npk',
        'pump_b' => 'calcium',
        'pump_c' => 'magnesium',
        'pump_d' => 'micro',
    ];

    /**
     * @return list<string>
     */
    public static function dosingRoles(): array
    {
        return self::DOSING_ROLES;
    }

    /**
     * @return list<string>
     */
    public static function dosingComponents(): array
    {
        return array_values(self::ROLE_COMPONENT_MAP);
    }

    public static function componentForRole(?string $role): ?string
    {
        if (! is_string($role) || trim($role) === '') {
            return null;
        }

        return self::ROLE_COMPONENT_MAP[trim($role)] ?? null;
    }

    public static function roleForComponent(?string $component): ?string
    {
        if (! is_string($component) || trim($component) === '') {
            return null;
        }

        $role = array_search(trim($component), self::ROLE_COMPONENT_MAP, true);

        return is_string($role) ? $role : null;
    }

    public static function isDosingRole(?string $role): bool
    {
        if (! is_string($role) || trim($role) === '') {
            return false;
        }

        return in_array(trim($role), self::DOSING_ROLES, true);
    }

    public static function isDosingComponent(?string $component): bool
    {
        if (! is_string($component) || trim($component) === '') {
            return false;
        }

        return in_array(trim($component), self::dosingComponents(), true);
    }
}
