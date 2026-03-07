<?php

namespace App\Services\AutomationScheduler;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

trait ResolvesAutomationRuntime
{
    protected function resolveAutomationRuntime(
        int $zoneId,
        string $warningContext = 'laravel scheduler'
    ): string {
        try {
            $runtime = DB::table('zones')
                ->where('id', $zoneId)
                ->value('automation_runtime');
        } catch (\Throwable $e) {
            Log::warning("Failed to resolve automation_runtime for {$warningContext}", [
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return 'ae2';
        }

        $normalized = strtolower(trim((string) $runtime));

        return $normalized !== '' ? $normalized : 'ae2';
    }
}
