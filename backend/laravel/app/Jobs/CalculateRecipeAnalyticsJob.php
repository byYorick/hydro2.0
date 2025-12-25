<?php

namespace App\Jobs;

use App\Services\RecipeAnalyticsService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;

class CalculateRecipeAnalyticsJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public function __construct(
        public int $zoneId,
        public ?int $growCycleId = null
    ) {
    }

    public function handle(RecipeAnalyticsService $service): void
    {
        try {
            $service->calculateAndStore($this->zoneId, $this->growCycleId);
        } catch (\Exception $e) {
            Log::error('Failed to calculate recipe analytics', [
                'zone_id' => $this->zoneId,
                'grow_cycle_id' => $this->growCycleId,
                'error' => $e->getMessage(),
            ]);
            throw $e;
        }
    }
}

