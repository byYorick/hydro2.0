<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Models\Zone;
use App\Models\ZoneManualSchedule;
use App\Services\AutomationScheduler\ManualScheduleService;
use App\Services\AutomationScheduler\SchedulerRuntimeHelper;
use Carbon\CarbonImmutable;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ManualScheduleServiceTest extends TestCase
{
    use RefreshDatabase;

    private ManualScheduleService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(ManualScheduleService::class);
    }

    public function test_mark_dispatched_is_idempotent_for_once(): void
    {
        $zone = Zone::factory()->create();
        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'lighting',
            'schedule_kind' => 'once',
            'run_at' => now('UTC')->subHour(),
            'payload' => [],
            'enabled' => true,
        ]);

        $at = SchedulerRuntimeHelper::nowUtc();

        $this->assertTrue($this->service->markDispatched($schedule, $at));
        $schedule->refresh();
        $this->assertFalse($schedule->enabled);
        $this->assertNotNull($schedule->last_dispatched_at);

        $this->assertFalse($this->service->markDispatched($schedule->fresh(), $at));
    }

    public function test_update_resets_once_dispatch_state_when_run_at_moves_to_future(): void
    {
        $zone = Zone::factory()->create();
        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'lighting',
            'schedule_kind' => 'once',
            'run_at' => now('UTC')->subHour(),
            'payload' => [],
            'enabled' => false,
        ]);
        $schedule->forceFill(['last_dispatched_at' => now('UTC')->subHour()])->save();

        $newRunAt = SchedulerRuntimeHelper::nowUtc()->addHours(2);

        $updated = $this->service->update($schedule, [
            'run_at' => $newRunAt->toIso8601String(),
            'enabled' => true,
        ]);

        $this->assertNull($updated->last_dispatched_at);
        $this->assertTrue($updated->enabled);
    }

    public function test_cannot_reenable_once_without_new_future_run_at(): void
    {
        $zone = Zone::factory()->create();
        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'lighting',
            'schedule_kind' => 'once',
            'run_at' => now('UTC')->subHour(),
            'payload' => [],
            'enabled' => false,
        ]);
        $schedule->forceFill(['last_dispatched_at' => now('UTC')->subHour()])->save();

        $this->expectException(\Illuminate\Validation\ValidationException::class);

        $this->service->update($schedule, ['enabled' => true]);
    }
}
