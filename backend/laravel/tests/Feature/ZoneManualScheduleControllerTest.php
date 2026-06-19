<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneManualSchedule;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneManualScheduleControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_agronomist_can_create_time_based_manual_schedule(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $response = $this->withToken($token)->postJson("/api/zones/{$zone->id}/manual-schedules", [
            'task_type' => 'irrigation',
            'schedule_kind' => 'time',
            'time_at' => '09:30',
            'days_of_week' => [1, 3, 5],
            'payload' => ['duration_sec' => 120],
            'label' => 'Утренний полив',
        ]);

        $response->assertCreated()
            ->assertJsonPath('data.task_type', 'irrigation')
            ->assertJsonPath('data.schedule_kind', 'time')
            ->assertJsonPath('data.time_at', '09:30')
            ->assertJsonPath('data.days_of_week', [1, 3, 5])
            ->assertJsonPath('data.payload.duration_sec', 120)
            ->assertJsonPath('data.enabled', true);

        $this->assertDatabaseHas('zone_manual_schedules', [
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_kind' => 'time',
            'label' => 'Утренний полив',
        ]);
    }

    public function test_agronomist_can_create_once_schedule(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $runAt = now('UTC')->addHours(2)->toIso8601String();

        $response = $this->withToken($token)->postJson("/api/zones/{$zone->id}/manual-schedules", [
            'task_type' => 'lighting',
            'schedule_kind' => 'once',
            'run_at' => $runAt,
        ]);

        $response->assertCreated()
            ->assertJsonPath('data.schedule_kind', 'once')
            ->assertJsonPath('data.task_type', 'lighting');
    }

    public function test_ae3_zone_rejects_non_executable_manual_schedule(): void
    {
        $zone = Zone::factory()->create(['automation_runtime' => 'ae3']);
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $response = $this->withToken($token)->postJson("/api/zones/{$zone->id}/manual-schedules", [
            'task_type' => 'ventilation',
            'schedule_kind' => 'window',
            'window_start' => '08:00',
            'window_end' => '20:00',
        ]);

        $response->assertUnprocessable()
            ->assertJsonValidationErrors(['task_type']);
    }

    public function test_operator_cannot_create_manual_schedule(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;

        $response = $this->withToken($token)->postJson("/api/zones/{$zone->id}/manual-schedules", [
            'task_type' => 'irrigation',
            'schedule_kind' => 'time',
            'time_at' => '09:30',
        ]);

        $response->assertForbidden();
    }

    public function test_manual_schedule_appears_in_schedule_workspace(): void
    {
        $zone = Zone::factory()->create(['automation_runtime' => 'ae3']);
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;

        ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_kind' => 'time',
            'time_at' => '10:00:00',
            'days_of_week' => [1, 2, 3, 4, 5],
            'payload' => ['duration_sec' => 90],
            'enabled' => true,
        ]);

        $response = $this->withToken($token)->getJson("/api/zones/{$zone->id}/schedule-workspace?horizon=24h");

        $response->assertOk()
            ->assertJsonPath('data.manual_schedules.0.task_type', 'irrigation')
            ->assertJsonPath('data.manual_schedules.0.schedule_kind', 'time');

        $windows = $response->json('data.plan.windows');
        $this->assertIsArray($windows);
        $manualWindows = array_values(array_filter(
            $windows,
            static fn (array $window): bool => ($window['origin'] ?? null) === 'manual',
        ));
        $this->assertNotEmpty($manualWindows);
    }

    public function test_agronomist_can_toggle_manual_schedule_enabled(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_kind' => 'time',
            'time_at' => '10:00:00',
            'payload' => [],
            'enabled' => true,
        ]);

        $response = $this->withToken($token)->putJson(
            "/api/zones/{$zone->id}/manual-schedules/{$schedule->id}",
            ['enabled' => false],
        );

        $response->assertOk()
            ->assertJsonPath('data.enabled', false);
    }

    public function test_agronomist_can_reschedule_once_after_dispatch(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'lighting',
            'schedule_kind' => 'once',
            'run_at' => now('UTC')->subHour(),
            'payload' => [],
            'enabled' => false,
        ]);
        $schedule->forceFill(['last_dispatched_at' => now('UTC')->subHour()])->save();

        $newRunAt = now('UTC')->addHours(3)->toIso8601String();

        $response = $this->withToken($token)->putJson(
            "/api/zones/{$zone->id}/manual-schedules/{$schedule->id}",
            ['run_at' => $newRunAt, 'enabled' => true],
        );

        $response->assertOk()
            ->assertJsonPath('data.enabled', true);

        $schedule->refresh();
        $this->assertNull($schedule->last_dispatched_at);
        $this->assertTrue($schedule->enabled);
    }

    public function test_manual_schedule_from_other_zone_returns_404_on_update(): void
    {
        $zoneA = Zone::factory()->create();
        $zoneB = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zoneA->id,
            'task_type' => 'irrigation',
            'schedule_kind' => 'time',
            'time_at' => '08:00:00',
            'payload' => [],
            'enabled' => true,
        ]);

        $response = $this->withToken($token)->putJson(
            "/api/zones/{$zoneB->id}/manual-schedules/{$schedule->id}",
            ['label' => 'hijack'],
        );

        $response->assertNotFound();
    }

    public function test_agronomist_can_delete_manual_schedule(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'lighting',
            'schedule_kind' => 'window',
            'window_start' => '06:00:00',
            'window_end' => '22:00:00',
            'payload' => [],
            'enabled' => true,
        ]);

        $response = $this->withToken($token)->deleteJson(
            "/api/zones/{$zone->id}/manual-schedules/{$schedule->id}",
        );

        $response->assertOk();
        $this->assertDatabaseMissing('zone_manual_schedules', ['id' => $schedule->id]);
    }
}
