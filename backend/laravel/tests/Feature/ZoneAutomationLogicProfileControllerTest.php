<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneAutomationLogicProfile;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationLogicProfileControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_upserts_and_returns_zone_automation_logic_profile(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);

        $payload = [
            'mode' => 'setup',
            'activate' => true,
            'subsystems' => $this->validSubsystemsPayload(),
        ];

        $response = $this->actingAs($user)
            ->postJson("/api/zones/{$zone->id}/automation-logic-profile", $payload);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.active_mode', 'setup')
            ->assertJsonPath('data.profiles.setup.mode', 'setup')
            ->assertJsonPath('data.profiles.setup.is_active', true)
            ->assertJsonPath('data.profiles.setup.subsystems.irrigation.execution.system_type', 'nft');

        $this->assertDatabaseHas('zone_automation_logic_profiles', [
            'zone_id' => $zone->id,
            'mode' => 'setup',
            'is_active' => true,
            'updated_by' => $user->id,
        ]);

        $showResponse = $this->actingAs($user)
            ->getJson("/api/zones/{$zone->id}/automation-logic-profile");

        $showResponse->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.active_mode', 'setup')
            ->assertJsonPath('data.profiles.setup.subsystems.irrigation.execution.interval_minutes', 20);
    }

    public function test_it_switches_active_profile_between_modes(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);

        $this->actingAs($user)->postJson("/api/zones/{$zone->id}/automation-logic-profile", [
            'mode' => 'setup',
            'activate' => true,
            'subsystems' => $this->validSubsystemsPayload(),
        ])->assertOk();

        $workingSubsystems = $this->validSubsystemsPayload();
        $workingSubsystems['irrigation']['execution']['interval_minutes'] = 30;

        $this->actingAs($user)->postJson("/api/zones/{$zone->id}/automation-logic-profile", [
            'mode' => 'working',
            'activate' => true,
            'subsystems' => $workingSubsystems,
        ])->assertOk()
            ->assertJsonPath('data.active_mode', 'working')
            ->assertJsonPath('data.profiles.working.is_active', true);

        $setup = ZoneAutomationLogicProfile::query()->where('zone_id', $zone->id)->where('mode', 'setup')->first();
        $working = ZoneAutomationLogicProfile::query()->where('zone_id', $zone->id)->where('mode', 'working')->first();

        $this->assertNotNull($setup);
        $this->assertNotNull($working);
        $this->assertFalse((bool) $setup?->is_active);
        $this->assertTrue((bool) $working?->is_active);
    }

    public function test_it_returns_null_active_mode_when_profiles_exist_but_none_active(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);

        $this->actingAs($user)->postJson("/api/zones/{$zone->id}/automation-logic-profile", [
            'mode' => 'setup',
            'activate' => false,
            'subsystems' => $this->validSubsystemsPayload(),
        ])->assertOk()
            ->assertJsonPath('data.active_mode', null)
            ->assertJsonPath('data.profiles.setup.is_active', false);

        $showResponse = $this->actingAs($user)
            ->getJson("/api/zones/{$zone->id}/automation-logic-profile");

        $showResponse->assertOk()
            ->assertJsonPath('data.active_mode', null)
            ->assertJsonPath('data.profiles.setup.mode', 'setup');
    }

    public function test_it_rejects_profile_update_for_viewer_role(): void
    {
        $zone = Zone::factory()->create();
        $viewer = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($viewer)
            ->postJson("/api/zones/{$zone->id}/automation-logic-profile", [
                'mode' => 'setup',
                'subsystems' => $this->validSubsystemsPayload(),
            ])
            ->assertForbidden();
    }

    public function test_it_rejects_legacy_targets_in_subsystems_payload(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);

        $payload = [
            'mode' => 'setup',
            'activate' => true,
            'subsystems' => [
                'ph' => [
                    'enabled' => true,
                    'targets' => [
                        'target' => 5.8,
                    ],
                ],
                'ec' => [
                    'enabled' => true,
                    'targets' => [
                        'target' => 1.6,
                    ],
                ],
                'irrigation' => [
                    'enabled' => true,
                    'targets' => [
                        'interval_minutes' => 20,
                        'duration_seconds' => 30,
                    ],
                ],
            ],
        ];

        $response = $this->actingAs($user)
            ->postJson("/api/zones/{$zone->id}/automation-logic-profile", $payload);

        $response->assertStatus(422)
            ->assertJsonValidationErrors([
                'subsystems.ph.targets',
                'subsystems.ec.targets',
                'subsystems.irrigation.targets',
            ]);
    }

    private function validSubsystemsPayload(): array
    {
        return [
            'ph' => [
                'enabled' => true,
                'execution' => [],
            ],
            'ec' => [
                'enabled' => true,
                'execution' => [],
            ],
            'irrigation' => [
                'enabled' => true,
                'execution' => [
                    'interval_minutes' => 20,
                    'duration_seconds' => 30,
                    'system_type' => 'nft',
                ],
            ],
        ];
    }
}
