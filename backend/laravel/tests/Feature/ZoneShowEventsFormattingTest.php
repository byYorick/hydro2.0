<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Inertia\Testing\AssertableInertia;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneShowEventsFormattingTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_show_formats_alert_updated_message_from_payload(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $this->insertZoneEvent($zone->id, 'ALERT_UPDATED', [
            'code' => 'BIZ_HIGH_TEMP',
            'error_count' => 5,
        ]);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page): void {
                $page->component('Zones/Show')
                    ->has('events', 1)
                    ->where('events.0.kind', 'ALERT_UPDATED')
                    ->where('events.0.message', 'Алерт BIZ_HIGH_TEMP обновлён (повторений: 5)');
            });
    }

    public function test_zone_show_formats_cycle_adjusted_subsystems_summary(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $this->insertZoneEvent($zone->id, 'CYCLE_ADJUSTED', [
            'subsystems' => [
                'ph' => [
                    'enabled' => true,
                    'targets' => ['min' => 5.7, 'max' => 6.1],
                ],
            ],
        ]);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page): void {
                $page->component('Zones/Show')
                    ->has('events', 1)
                    ->where('events.0.kind', 'CYCLE_ADJUSTED')
                    ->where('events.0.message', 'Цикл скорректирован: pH 5.7–6.1');
            });
    }

    public function test_zone_show_formats_recipe_revision_change_message(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $this->insertZoneEvent($zone->id, 'CYCLE_RECIPE_REVISION_CHANGED', [
            'from_revision_id' => 2,
            'to_revision_id' => 3,
            'apply_mode' => 'now',
        ]);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page): void {
                $page->component('Zones/Show')
                    ->has('events', 1)
                    ->where('events.0.kind', 'CYCLE_RECIPE_REVISION_CHANGED')
                    ->where('events.0.message', 'Смена ревизии рецепта: #2 -> #3 (немедленно)');
            });
    }

    public function test_zone_show_localizes_ae_task_failed_message_from_payload(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $this->insertZoneEvent($zone->id, 'AE_TASK_FAILED', [
            'error_code' => 'zone_correction_config_missing_critical',
            'error_message' => 'Zone 1 correction_config.base missing required fields: runtime, timing, dosing, retry, tolerance, controllers, safety; fail-closed for critical correction parameters',
            'message' => 'Zone 1 correction_config.base missing required fields: runtime, timing, dosing, retry, tolerance, controllers, safety; fail-closed for critical correction parameters',
            'type' => 'automation_engine',
        ]);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page): void {
                $page->component('Zones/Show')
                    ->has('events', 1)
                    ->where('events.0.kind', 'AE_TASK_FAILED')
                    ->where(
                        'events.0.message',
                        'В зоне 1 в correction_config.base отсутствуют обязательные поля: runtime, timing, dosing, retry, tolerance, controllers, safety; критические параметры коррекции переведены в fail-closed режим.'
                    );
            });
    }

    public function test_zone_show_exposes_expanded_ae3_task_failed_alert_message(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        Alert::query()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_ae3_task_failed',
            'type' => 'Ошибка задачи автоматики',
            'status' => 'ACTIVE',
            'category' => 'operations',
            'severity' => 'error',
            'details' => [
                'task_id' => 314,
                'task_type' => 'cycle_start',
                'stage' => 'tank_recirc',
                'workflow_phase' => 'ready',
                'topology' => 'two_tank',
                'stage_retry_count' => 2,
                'error_code' => 'ae3_task_execution_timeout',
                'error_message' => 'Task execution exceeded runtime timeout',
                'message' => 'Task execution exceeded runtime timeout',
            ],
            'error_count' => 1,
            'first_seen_at' => now(),
            'last_seen_at' => now(),
            'created_at' => now(),
        ]);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page): void {
                $page->component('Zones/Show')
                    ->has('alerts', 1)
                    ->where('alerts.0.title', 'Ошибка задачи автоматики')
                    ->where(
                        'alerts.0.message',
                        'Задача AE3 #314 (cycle_start) завершилась с ошибкой (код: ae3_task_execution_timeout): этап tank_recirc, workflow ready, topology two_tank, retry 2. Причина: Выполнение задачи превысило допустимый runtime timeout.'
                    );
            });
    }

    private function insertZoneEvent(int $zoneId, string $type, array $payload): void
    {
        $payloadColumn = DB::getSchemaBuilder()->hasColumn('zone_events', 'payload_json')
            ? 'payload_json'
            : 'details';

        DB::table('zone_events')->insert([
            'zone_id' => $zoneId,
            'type' => $type,
            $payloadColumn => json_encode($payload),
            'created_at' => now(),
        ]);
    }
}
