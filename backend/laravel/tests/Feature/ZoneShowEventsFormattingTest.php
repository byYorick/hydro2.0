<?php

namespace Tests\Feature;

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
