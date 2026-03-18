<?php

namespace Tests\Unit\Services;

use App\Models\Greenhouse;
use App\Models\GreenhouseAutomationLogicProfile;
use App\Models\User;
use App\Services\GreenhouseAutomationLogicProfileService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class GreenhouseAutomationLogicProfileServiceTest extends TestCase
{
    use RefreshDatabase;

    private GreenhouseAutomationLogicProfileService $service;

    protected function setUp(): void
    {
        parent::setUp();

        $this->service = app(GreenhouseAutomationLogicProfileService::class);
    }

    public function test_it_returns_active_allowed_profile_when_present(): void
    {
        $greenhouse = Greenhouse::factory()->create();

        GreenhouseAutomationLogicProfile::query()->create([
            'greenhouse_id' => $greenhouse->id,
            'mode' => GreenhouseAutomationLogicProfile::MODE_SETUP,
            'is_active' => false,
            'subsystems' => ['climate' => ['enabled' => true, 'execution' => ['interval_sec' => 600]]],
        ]);

        $working = GreenhouseAutomationLogicProfile::query()->create([
            'greenhouse_id' => $greenhouse->id,
            'mode' => GreenhouseAutomationLogicProfile::MODE_WORKING,
            'is_active' => true,
            'subsystems' => ['climate' => ['enabled' => true, 'execution' => ['interval_sec' => 120]]],
        ]);

        $resolved = $this->service->resolveActiveProfileForGreenhouse($greenhouse->id);

        $this->assertNotNull($resolved);
        $this->assertSame($working->id, $resolved?->id);
        $this->assertSame(GreenhouseAutomationLogicProfile::MODE_WORKING, $resolved?->mode);
    }

    public function test_it_upserts_greenhouse_profile_and_returns_payload(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $user = User::factory()->create();

        $profile = $this->service->upsertProfile(
            greenhouse: $greenhouse,
            mode: GreenhouseAutomationLogicProfile::MODE_SETUP,
            subsystems: [
                'climate' => [
                    'enabled' => true,
                    'execution' => [
                        'interval_sec' => 300,
                        'temperature' => ['day' => 24, 'night' => 19],
                    ],
                ],
            ],
            activate: true,
            userId: (int) $user->id,
        );

        $payload = $this->service->getProfilesPayload($greenhouse);

        $this->assertSame(GreenhouseAutomationLogicProfile::MODE_SETUP, $profile->mode);
        $this->assertSame(GreenhouseAutomationLogicProfile::MODE_SETUP, $payload['active_mode']);
        $this->assertSame(300, data_get($payload, 'profiles.setup.subsystems.climate.execution.interval_sec'));
        $this->assertSame(300, data_get($profile->command_plans, 'plans.climate.execution.interval_sec'));
    }
}
