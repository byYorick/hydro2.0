<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Greenhouse;
use App\Services\AutomationConfigRegistry;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationConfigControllerGreenhouseLogicProfileTest extends TestCase
{
    use RefreshDatabase;

    public function test_agronomist_can_read_greenhouse_logic_profile_without_explicit_assignment(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();

        $response = $this->actingAs($user)
            ->getJson("/api/automation-configs/greenhouse/{$greenhouse->id}/".AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE);

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.namespace', AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE)
            ->assertJsonPath('data.scope_type', 'greenhouse')
            ->assertJsonPath('data.scope_id', $greenhouse->id)
            ->assertJsonPath('data.storage_ready', true);
    }

    public function test_agronomist_can_update_greenhouse_logic_profile_without_explicit_assignment(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();

        $payload = [
            'active_mode' => 'setup',
            'profiles' => [
                'setup' => [
                    'mode' => 'setup',
                    'is_active' => true,
                    'subsystems' => [
                        'climate' => [
                            'enabled' => true,
                            'execution' => [
                                'strategy' => 'greenhouse_runtime',
                            ],
                        ],
                    ],
                    'updated_at' => now()->toIso8601String(),
                ],
            ],
        ];

        $response = $this->actingAs($user)
            ->putJson("/api/automation-configs/greenhouse/{$greenhouse->id}/".AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE, [
                'payload' => $payload,
            ]);

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.active_mode', 'setup')
            ->assertJsonPath('data.profiles.setup.subsystems.climate.enabled', true)
            ->assertJsonPath('data.payload.profiles.setup.subsystems.climate.execution.strategy', 'greenhouse_runtime');
    }
}
