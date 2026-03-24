<?php

namespace Tests\Unit\Services;

use App\Models\Zone;
use App\Models\ZoneAutomationLogicProfile;
use App\Models\User;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneAutomationLogicProfileService;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationLogicProfileServiceTest extends TestCase
{
    use RefreshDatabase;

    private ZoneAutomationLogicProfileService $service;

    protected function setUp(): void
    {
        parent::setUp();

        $this->service = app(ZoneAutomationLogicProfileService::class);
    }

    public function test_it_returns_active_allowed_profile_when_present(): void
    {
        $zone = Zone::factory()->create();

        $this->storeProfiles($zone->id, [
            'active_mode' => ZoneAutomationLogicProfile::MODE_WORKING,
            'profiles' => [
                ZoneAutomationLogicProfile::MODE_SETUP => [
                    'mode' => ZoneAutomationLogicProfile::MODE_SETUP,
                    'is_active' => false,
                    'subsystems' => ['irrigation' => ['enabled' => true, 'execution' => ['interval_sec' => 300]]],
                ],
                ZoneAutomationLogicProfile::MODE_WORKING => [
                    'mode' => ZoneAutomationLogicProfile::MODE_WORKING,
                    'is_active' => true,
                    'subsystems' => ['irrigation' => ['enabled' => true, 'execution' => ['interval_sec' => 60]]],
                ],
            ],
        ]);

        $resolved = $this->service->resolveActiveProfileForZone($zone->id);

        $this->assertNotNull($resolved);
        $this->assertSame(ZoneAutomationLogicProfile::MODE_WORKING, $resolved?->mode);
    }

    public function test_it_returns_null_when_no_active_mode_is_set(): void
    {
        $zone = Zone::factory()->create();

        $this->storeProfiles($zone->id, [
            'active_mode' => null,
            'profiles' => [
                ZoneAutomationLogicProfile::MODE_SETUP => [
                    'mode' => ZoneAutomationLogicProfile::MODE_SETUP,
                    'is_active' => false,
                    'subsystems' => ['irrigation' => ['enabled' => true, 'execution' => ['interval_sec' => 1800]]],
                ],
            ],
        ]);

        $resolved = $this->service->resolveActiveProfileForZone($zone->id);
        $payload = $this->service->getProfilesPayload($zone);

        $this->assertNull($resolved);
        $this->assertNull($payload['active_mode']);
    }

    public function test_it_returns_null_when_no_allowed_profiles_exist(): void
    {
        $zone = Zone::factory()->create();

        $this->storeProfiles($zone->id, [
            'active_mode' => null,
            'profiles' => [],
        ]);

        $resolved = $this->service->resolveActiveProfileForZone($zone->id);
        $payload = $this->service->getProfilesPayload($zone);

        $this->assertNull($resolved);
        $this->assertNull($payload['active_mode']);
    }

    public function test_it_emits_zone_event_after_profile_upsert(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create();
        $subsystems = [
            'irrigation' => ['enabled' => true, 'execution' => ['interval_sec' => 120]],
            'ph' => ['enabled' => true, 'execution' => ['target' => 5.8]],
            'ec' => ['enabled' => true, 'execution' => ['target' => 1.7]],
        ];

        $profile = $this->service->upsertProfile(
            zone: $zone,
            mode: ZoneAutomationLogicProfile::MODE_SETUP,
            subsystems: $subsystems,
            activate: true,
            userId: (int) $user->id,
        );

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'AUTOMATION_LOGIC_PROFILE_UPDATED',
            'entity_type' => 'automation_logic_profile',
            'entity_id' => (string) $profile->id,
        ]);

        $event = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'AUTOMATION_LOGIC_PROFILE_UPDATED')
            ->orderByDesc('id')
            ->first(['payload_json']);

        $this->assertNotNull($event);
        $payloadRaw = $event->payload_json ?? null;
        $payload = is_string($payloadRaw) ? json_decode($payloadRaw, true) : (is_array($payloadRaw) ? $payloadRaw : null);
        $this->assertIsArray($payload);
        $this->assertSame((int) $user->id, $payload['user_id'] ?? null);
        $this->assertSame(ZoneAutomationLogicProfile::MODE_SETUP, $payload['mode'] ?? null);
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function storeProfiles(int $zoneId, array $payload): void
    {
        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            $payload,
        );
    }
}
