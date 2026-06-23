<?php

namespace Tests\Feature;

use App\Models\Command;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCommandsHistoryTest extends TestCase
{
    use RefreshDatabase;

    private function revokeZoneAccess(User $user, Zone $zone): void
    {
        DB::table('user_greenhouses')
            ->where('user_id', $user->id)
            ->where('greenhouse_id', $zone->greenhouse_id)
            ->delete();

        DB::table('user_zones')
            ->where('user_id', $user->id)
            ->where('zone_id', $zone->id)
            ->delete();
    }

    public function test_zone_commands_endpoint_returns_paginated_history(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        Command::create([
            'zone_id' => $zone->id,
            'cmd_id' => 'cmd-history-1',
            'cmd' => 'run_pump',
            'status' => Command::STATUS_DONE,
        ]);

        Command::create([
            'zone_id' => $zone->id,
            'cmd_id' => 'cmd-history-2',
            'cmd' => 'dose',
            'status' => Command::STATUS_ERROR,
            'error_code' => 'pump_busy',
            'error_message' => 'Pump is already running',
        ]);

        $response = $this->actingAs($user)
            ->getJson("/api/zones/{$zone->id}/commands?per_page=10");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonCount(2, 'data')
            ->assertJsonStructure([
                'data' => [[
                    'cmd_id',
                    'status',
                    'cmd',
                    'human_error_message',
                ]],
                'meta' => ['current_page', 'last_page', 'per_page', 'total'],
            ]);

        $cmdIds = collect($response->json('data'))->pluck('cmd_id')->all();
        $this->assertEqualsCanonicalizing(['cmd-history-1', 'cmd-history-2'], $cmdIds);

        $errorRow = collect($response->json('data'))->firstWhere('cmd_id', 'cmd-history-2');
        $this->assertIsArray($errorRow);
        $this->assertNotEmpty($errorRow['human_error_message']);
    }

    public function test_zone_commands_endpoint_requires_zone_access(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $this->revokeZoneAccess($viewer, $zone);

        $this->actingAs($viewer)
            ->getJson("/api/zones/{$zone->id}/commands")
            ->assertStatus(403);
    }
}
