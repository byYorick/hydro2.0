<?php

namespace Tests\Unit;

use App\Jobs\CompleteSimulationJob;
use App\Jobs\StopSimulationNodesJob;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Queue;
use Tests\RefreshDatabase;
use Tests\TestCase;

class CompleteSimulationJobTest extends TestCase
{
    use RefreshDatabase;

    public function test_complete_simulation_job_updates_meta_and_dispatches_stop(): void
    {
        Queue::fake();

        $zone = Zone::factory()->create();
        $simStart = now()->subMinutes(5);
        Carbon::setTestNow($simStart->copy()->addMinutes(5));

        $simulation = ZoneSimulation::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'running',
            'scenario' => [
                'recipe_id' => 1,
                'simulation' => [
                    'real_started_at' => $simStart->toIso8601String(),
                    'sim_started_at' => $simStart->toIso8601String(),
                    'real_duration_minutes' => 10,
                    'time_scale' => 12,
                ],
            ],
        ]);

        $jobId = 'sim_job_complete';
        Cache::put("simulation:{$jobId}", [
            'status' => 'processing',
            'simulation_id' => $simulation->id,
        ], 3600);

        $job = new CompleteSimulationJob($simulation->id, $jobId);
        $job->handle();

        $simulation->refresh();
        $this->assertSame('completed', $simulation->status);

        $simMeta = $simulation->scenario['simulation'] ?? [];
        $endedAt = Carbon::parse($simMeta['real_ended_at']);
        $this->assertSame(now()->timestamp, $endedAt->timestamp);

        $expectedSimEnd = $simStart->copy()
            ->addSeconds(10 * 60 * 12)
            ->toIso8601String();
        $this->assertSame($expectedSimEnd, $simMeta['sim_ended_at']);

        $cached = Cache::get("simulation:{$jobId}");
        $this->assertSame('completed', $cached['status']);
        $this->assertSame($simulation->id, $cached['simulation_id']);

        Queue::assertPushed(StopSimulationNodesJob::class, function ($job) use ($zone, $simulation, $jobId) {
            return $job->zoneId === $zone->id
                && $job->simulationId === $simulation->id
                && $job->jobId === $jobId;
        });

        Carbon::setTestNow();
    }
}
