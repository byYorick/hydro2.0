<?php

namespace App\Jobs;

use App\Models\ZoneSimulation;
use App\Jobs\StopSimulationNodesJob;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;

class CompleteSimulationJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 30;

    /**
     * Create a new job instance.
     */
    public function __construct(
        public int $simulationId,
        public string $jobId
    ) {
        //
    }

    /**
     * Execute the job.
     */
    public function handle(): void
    {
        $simulation = ZoneSimulation::find($this->simulationId);
        if (! $simulation) {
            Log::warning('CompleteSimulationJob: simulation not found', [
                'simulation_id' => $this->simulationId,
                'job_id' => $this->jobId,
            ]);
            return;
        }

        if ($simulation->status !== 'running') {
            return;
        }

        $scenario = $simulation->scenario ?? [];
        if (is_array($scenario)) {
            $simMeta = [];
            if (isset($scenario['simulation']) && is_array($scenario['simulation'])) {
                $simMeta = $scenario['simulation'];
            }
            $simMeta['real_ended_at'] = now()->toIso8601String();

            $realDurationMinutes = $simMeta['real_duration_minutes'] ?? null;
            $timeScale = $simMeta['time_scale'] ?? null;
            $simStartedAt = $simMeta['sim_started_at'] ?? null;
            if (is_numeric($realDurationMinutes) && is_numeric($timeScale) && $simStartedAt) {
                $simEndedAt = Carbon::parse($simStartedAt)
                    ->addSeconds((float) $realDurationMinutes * 60 * (float) $timeScale);
                $simMeta['sim_ended_at'] = $simEndedAt->toIso8601String();
            }
            $scenario['simulation'] = $simMeta;
        }

        $simulation->update([
            'status' => 'completed',
            'scenario' => $scenario,
        ]);

        Cache::put("simulation:{$this->jobId}", [
            'status' => 'completed',
            'completed_at' => now()->toIso8601String(),
            'simulation_id' => $simulation->id,
        ], 3600);

        StopSimulationNodesJob::dispatch($simulation->zone_id, $simulation->id, $this->jobId);
    }
}
