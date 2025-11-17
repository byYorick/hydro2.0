<?php

namespace App\Jobs;

use App\Services\PredictionService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;

class GeneratePredictionsJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    /**
     * Execute the job.
     */
    public function handle(PredictionService $predictionService): void
    {
        Log::info('Starting predictions generation for active zones');

        $count = $predictionService->generatePredictionsForActiveZones(['ph', 'ec']);

        Log::info('Predictions generation completed', [
            'predictions_created' => $count,
        ]);
    }
}
