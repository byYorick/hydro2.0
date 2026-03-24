<?php

namespace App\Services;

final class ZoneLogicProfileCatalog
{
    public const MODE_SETUP = 'setup';
    public const MODE_WORKING = 'working';

    /**
     * @return list<string>
     */
    public static function allowedModes(): array
    {
        return [
            self::MODE_SETUP,
            self::MODE_WORKING,
        ];
    }
}
