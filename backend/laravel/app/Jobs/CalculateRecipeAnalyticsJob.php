<?php

namespace App\Jobs;

use App\Models\ZoneRecipeInstance;
use App\Models\RecipeAnalytics;
use App\Models\Alert;
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
        public ?int $recipeInstanceId = null
    ) {
    }

    public function handle(RecipeAnalyticsService $service): void
    {
        try {
            $service->calculateAndStore($this->zoneId, $this->recipeInstanceId);
        } catch (\Exception $e) {
            Log::error('Failed to calculate recipe analytics', [
                'zone_id' => $this->zoneId,
                'error' => $e->getMessage(),
            ]);
            throw $e;
        }
    }
}

