<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneAutomationLogicProfile;
use App\Services\PythonBridgeService;
use Mockery\MockInterface;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCommandSystemTypeLockTest extends TestCase
{
    use RefreshDatabase;

    public function test_adjust_rejects_system_type_change_for_active_cycle(): void
    {
        $zone = Zone::factory()->create();
        GrowCycle::factory()->running()->create([
            'zone_id' => $zone->id,
            'greenhouse_id' => $zone->greenhouse_id,
            'settings' => [
                'irrigation' => [
                    'system_type' => 'drip',
                ],
            ],
        ]);

        ZoneAutomationLogicProfile::query()->create([
            'zone_id' => $zone->id,
            'mode' => ZoneAutomationLogicProfile::MODE_WORKING,
            'is_active' => true,
            'subsystems' => [
                'ph' => [
                    'enabled' => true,
                    'targets' => ['target' => 5.8],
                ],
                'ec' => [
                    'enabled' => true,
                    'targets' => ['target' => 1.6],
                ],
                'irrigation' => [
                    'enabled' => true,
                    'targets' => [
                        'interval_minutes' => 20,
                        'duration_seconds' => 30,
                        'system_type' => 'nft',
                    ],
                ],
            ],
        ]);

        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $payload = $this->buildAdjustPayload('working');

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/commands", $payload);

        $response->assertStatus(422)
            ->assertJson([
                'status' => 'error',
                'code' => 'SYSTEM_TYPE_LOCKED',
            ]);
    }

    public function test_adjust_allows_same_system_type_for_active_cycle(): void
    {
        $zone = Zone::factory()->create();
        GrowCycle::factory()->running()->create([
            'zone_id' => $zone->id,
            'greenhouse_id' => $zone->greenhouse_id,
            'settings' => [
                'irrigation' => [
                    'system_type' => 'drip',
                ],
            ],
        ]);

        ZoneAutomationLogicProfile::query()->create([
            'zone_id' => $zone->id,
            'mode' => ZoneAutomationLogicProfile::MODE_WORKING,
            'is_active' => true,
            'subsystems' => [
                'ph' => [
                    'enabled' => true,
                    'targets' => ['target' => 5.8],
                ],
                'ec' => [
                    'enabled' => true,
                    'targets' => ['target' => 1.6],
                ],
                'irrigation' => [
                    'enabled' => true,
                    'targets' => [
                        'interval_minutes' => 20,
                        'duration_seconds' => 30,
                        'system_type' => 'drip',
                    ],
                ],
            ],
        ]);

        $this->mock(PythonBridgeService::class, function (MockInterface $mock): void {
            $mock->shouldReceive('sendZoneCommand')->once()->andReturn('cmd-123');
        });

        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('test')->plainTextToken;

        $payload = $this->buildAdjustPayload('working');

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/commands", $payload);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.command_id', 'cmd-123');
    }

    private function buildAdjustPayload(string $profileMode): array
    {
        return [
            'type' => 'GROWTH_CYCLE_CONFIG',
            'params' => [
                'mode' => 'adjust',
                'profile_mode' => $profileMode,
            ],
        ];
    }
}
