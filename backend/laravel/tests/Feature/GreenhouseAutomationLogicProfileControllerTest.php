<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\GreenhouseAutomationLogicProfile;
use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

class GreenhouseAutomationLogicProfileControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_upserts_and_returns_greenhouse_automation_logic_profile(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);

        $response = $this->actingAs($user)
            ->postJson("/api/greenhouses/{$greenhouse->id}/automation-logic-profile", [
                'mode' => 'setup',
                'activate' => true,
                'subsystems' => $this->validSubsystemsPayload(),
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.active_mode', 'setup')
            ->assertJsonPath('data.profiles.setup.mode', 'setup')
            ->assertJsonPath('data.profiles.setup.is_active', true)
            ->assertJsonPath('data.profiles.setup.subsystems.climate.execution.interval_sec', 300);

        $this->assertDatabaseHas('greenhouse_automation_logic_profiles', [
            'greenhouse_id' => $greenhouse->id,
            'mode' => 'setup',
            'is_active' => true,
            'updated_by' => $user->id,
        ]);

        $profile = GreenhouseAutomationLogicProfile::query()
            ->where('greenhouse_id', $greenhouse->id)
            ->where('mode', 'setup')
            ->first();

        $this->assertNotNull($profile);
        $this->assertSame(1, data_get($profile?->command_plans, 'schema_version'));
        $this->assertSame(300, data_get($profile?->command_plans, 'plans.climate.execution.interval_sec'));

        $this->actingAs($user)
            ->getJson("/api/greenhouses/{$greenhouse->id}/automation-logic-profile")
            ->assertOk()
            ->assertJsonPath('data.active_mode', 'setup')
            ->assertJsonPath('data.profiles.setup.subsystems.climate.execution.temperature.day', 24);
    }

    public function test_it_rejects_unsupported_subsystems_for_greenhouse_profile(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $user = User::factory()->create(['role' => 'agronomist']);

        $response = $this->actingAs($user)
            ->postJson("/api/greenhouses/{$greenhouse->id}/automation-logic-profile", [
                'mode' => 'setup',
                'activate' => true,
                'subsystems' => [
                    'climate' => [
                        'enabled' => true,
                        'execution' => [
                            'interval_sec' => 300,
                        ],
                    ],
                    'lighting' => [
                        'enabled' => true,
                    ],
                ],
            ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors([
                'subsystems.lighting',
            ]);
    }

    private function validSubsystemsPayload(): array
    {
        return [
            'climate' => [
                'enabled' => true,
                'execution' => [
                    'interval_sec' => 300,
                    'temperature' => [
                        'day' => 24,
                        'night' => 20,
                    ],
                    'humidity' => [
                        'day' => 60,
                        'night' => 70,
                    ],
                    'vent_control' => [
                        'min_open_percent' => 15,
                        'max_open_percent' => 85,
                    ],
                ],
            ],
        ];
    }
}
