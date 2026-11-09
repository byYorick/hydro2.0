<?php

declare(strict_types=1);

namespace App\Services\AutomationScheduler;

use App\Exceptions\UnsupportedHydroponicSystemException;
use App\Services\HydroponicSystemGuard;
use Illuminate\Support\Facades\Log;

/**
 * Не даёт scheduler записать гидравлический intent для неподдерживаемого hydro_system.
 * Свет и явный diagnostics generic_cycle_start не блокируются.
 */
final class HydroponicDispatchGate
{
    public function blockCode(int $zoneId, string $aeTaskType, string $topology): ?string
    {
        $normalizedTopology = strtolower(trim($topology));
        $hydraulic = in_array($aeTaskType, ['irrigation_start', 'solution_topup', 'solution_change'], true)
            || ($aeTaskType === 'cycle_start' && ! in_array($normalizedTopology, ['generic_cycle_start', 'lighting_tick'], true));
        if (! $hydraulic) {
            return null;
        }

        try {
            app(HydroponicSystemGuard::class)->assertZoneIrrigationExecutable($zoneId);
        } catch (UnsupportedHydroponicSystemException $exception) {
            Log::warning('scheduler_intent_blocked_unsupported_hydroponic_system', [
                'zone_id' => $zoneId,
                'task_type' => $aeTaskType,
                'requested_type' => $exception->requestedType,
                'supported_types' => $exception->supportedTypes,
            ]);

            return $exception->errorCode;
        }

        return null;
    }
}
