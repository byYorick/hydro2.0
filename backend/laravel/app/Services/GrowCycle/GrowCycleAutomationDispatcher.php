<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Models\GrowCycle;
use Illuminate\Support\Facades\Log;

/**
 * Раньше диспатчил start-cycle в AE. После волны 10 ingress удалён —
 * тик automation-engine 1.0.0 сам ведёт посадку.
 */
class GrowCycleAutomationDispatcher
{
    public function dispatchAutomationStartCycle(GrowCycle $cycle): void
    {
        Log::info('Grow cycle start-cycle dispatch skipped after cutover', [
            'grow_cycle_id' => (int) $cycle->id,
            'zone_id' => (int) $cycle->zone_id,
        ]);
    }

    public function buildIdempotencyKey(int $zoneId, int $cycleId): string
    {
        return sprintf('grow-cycle-%d-%d', $zoneId, $cycleId);
    }
}
