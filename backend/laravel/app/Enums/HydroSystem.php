<?php

declare(strict_types=1);

namespace App\Enums;

/**
 * Канон hydro_system из ADR-0001. Список значений и флаг implemented
 * читаются из schemas/hydro_system.enum.json, этот enum — имена для кода.
 */
enum HydroSystem: string
{
    case Drip = 'drip';
    case EbbFlow = 'ebb_flow';
    case Nft = 'nft';
    case Dwc = 'dwc';
}
