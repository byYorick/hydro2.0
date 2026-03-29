<?php

namespace App\Support;

final class PumpCalibrationCatalog
{
    public const DOSING_ROLES = [
        'ph_acid_pump',
        'ph_base_pump',
        'ec_npk_pump',
        'ec_calcium_pump',
        'ec_magnesium_pump',
        'ec_micro_pump',
    ];

    public const ROLE_COMPONENT_MAP = [
        'ph_acid_pump' => 'ph_down',
        'ph_base_pump' => 'ph_up',
        'ec_npk_pump' => 'npk',
        'ec_calcium_pump' => 'calcium',
        'ec_magnesium_pump' => 'magnesium',
        'ec_micro_pump' => 'micro',
    ];

    /**
     * @return list<string>
     */
    public static function dosingRoles(): array
    {
        return self::DOSING_ROLES;
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
}
