<?php

namespace Tests\Unit\Helpers;

use App\Helpers\ZoneAccessHelper;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\DatabaseTransactions;
use Illuminate\Support\Facades\Config;
use Tests\TestCase;

class ZoneAccessHelperTest extends TestCase
{
    use DatabaseTransactions;

    public function test_legacy_mode_keeps_historical_access_for_non_admin(): void
    {
        Config::set('access_control.mode', 'legacy');

        $user = User::factory()->create(['role' => 'viewer']);
        $zoneA = Zone::factory()->create();
        $zoneB = Zone::factory()->create();

        $this->assertTrue(ZoneAccessHelper::canAccessZone($user, $zoneA));
        $this->assertTrue(ZoneAccessHelper::canAccessZone($user, $zoneB));

        $zoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        $this->assertContains($zoneA->id, $zoneIds);
        $this->assertContains($zoneB->id, $zoneIds);
    }

    public function test_shadow_mode_returns_legacy_result_without_assignments(): void
    {
        Config::set('access_control.mode', 'shadow');

        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $greenhouse = $zone->greenhouse;

        $this->assertTrue(ZoneAccessHelper::canAccessZone($user, $zone));
        $this->assertTrue(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse));
    }

    public function test_enforce_mode_denies_access_without_assignments(): void
    {
        Config::set('access_control.mode', 'enforce');

        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $greenhouse = $zone->greenhouse;

        $this->assertFalse(ZoneAccessHelper::canAccessZone($user, $zone));
        $this->assertFalse(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse));
        $this->assertSame([], ZoneAccessHelper::getAccessibleZoneIds($user));
    }

    public function test_enforce_mode_grants_access_via_greenhouse_or_direct_zone_assignment(): void
    {
        Config::set('access_control.mode', 'enforce');

        $user = User::factory()->create(['role' => 'viewer']);

        $greenhouseA = Greenhouse::factory()->create();
        $greenhouseB = Greenhouse::factory()->create();

        $zoneA = Zone::factory()->create(['greenhouse_id' => $greenhouseA->id]);
        $zoneB = Zone::factory()->create(['greenhouse_id' => $greenhouseB->id]);

        $user->greenhouses()->attach($greenhouseA->id);
        $user->zones()->attach($zoneB->id);

        $this->assertTrue(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouseA));
        $this->assertFalse(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouseB));

        $this->assertTrue(ZoneAccessHelper::canAccessZone($user, $zoneA));
        $this->assertTrue(ZoneAccessHelper::canAccessZone($user, $zoneB));

        $zoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        sort($zoneIds);
        $this->assertSame([$zoneA->id, $zoneB->id], $zoneIds);
    }

    public function test_enforce_mode_hides_unassigned_nodes_for_non_admin(): void
    {
        Config::set('access_control.mode', 'enforce');

        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();

        $assignedNode = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $unassignedNode = DeviceNode::factory()->create([
            'zone_id' => null,
            'status' => 'online',
        ]);

        $user->zones()->attach($zone->id);

        $nodeIds = ZoneAccessHelper::getAccessibleNodeIds($user);
        sort($nodeIds);

        $this->assertSame([$assignedNode->id], $nodeIds);
        $this->assertNotContains($unassignedNode->id, $nodeIds);
    }
}
