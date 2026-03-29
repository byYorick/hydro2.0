<?php

namespace Tests\Unit\Helpers;

use App\Helpers\ZoneAccessHelper;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\DatabaseTransactions;
use Illuminate\Support\Facades\Schema;
use Tests\TestCase;

class ZoneAccessHelperTest extends TestCase
{
    use DatabaseTransactions;

    public function test_strict_access_denies_zone_and_greenhouse_without_assignments(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $greenhouse = $zone->greenhouse;
        $user->greenhouses()->sync([]);
        $user->zones()->sync([]);

        $this->assertFalse(ZoneAccessHelper::canAccessZone($user, $zone));
        $this->assertFalse(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse));
        $this->assertSame([], ZoneAccessHelper::getAccessibleGreenhouseIds($user));
        $this->assertSame([], ZoneAccessHelper::getAccessibleZoneIds($user));
    }

    public function test_strict_access_fails_closed_when_assignment_tables_are_unavailable(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $greenhouse = $zone->greenhouse;
        $user->greenhouses()->sync([]);
        $user->zones()->sync([]);

        Schema::shouldReceive('hasTable')->with('user_zones')->andReturn(false);
        Schema::shouldReceive('hasTable')->with('user_greenhouses')->andReturn(false);

        $this->assertFalse(ZoneAccessHelper::canAccessZone($user, $zone));
        $this->assertFalse(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse));
        $this->assertSame([], ZoneAccessHelper::getAccessibleGreenhouseIds($user));
        $this->assertSame([], ZoneAccessHelper::getAccessibleZoneIds($user));
        $this->assertSame([], ZoneAccessHelper::getAccessibleNodeIds($user));
    }

    public function test_strict_access_grants_access_via_greenhouse_or_direct_zone_assignment(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        $greenhouseA = Greenhouse::factory()->create();
        $greenhouseB = Greenhouse::factory()->create();

        $zoneA = Zone::factory()->create(['greenhouse_id' => $greenhouseA->id]);
        $zoneB = Zone::factory()->create(['greenhouse_id' => $greenhouseB->id]);

        $user->greenhouses()->sync([$greenhouseA->id]);
        $user->zones()->sync([$zoneB->id]);

        $this->assertTrue(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouseA));
        $this->assertFalse(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouseB));

        $greenhouseIds = ZoneAccessHelper::getAccessibleGreenhouseIds($user);
        $this->assertSame([$greenhouseA->id], $greenhouseIds);

        $this->assertTrue(ZoneAccessHelper::canAccessZone($user, $zoneA));
        $this->assertTrue(ZoneAccessHelper::canAccessZone($user, $zoneB));

        $zoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        sort($zoneIds);
        $this->assertSame([$zoneA->id, $zoneB->id], $zoneIds);
    }

    public function test_strict_access_hides_unassigned_nodes_for_viewer(): void
    {
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

        $user->greenhouses()->sync([]);
        $user->zones()->sync([$zone->id]);

        $nodeIds = ZoneAccessHelper::getAccessibleNodeIds($user);
        sort($nodeIds);

        $this->assertSame([$assignedNode->id], $nodeIds);
        $this->assertNotContains($unassignedNode->id, $nodeIds);
        $this->assertFalse(ZoneAccessHelper::canAccessNode($user, $unassignedNode));
    }

    public function test_agronomist_can_access_unassigned_nodes_without_zone_assignment(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $unassignedNode = DeviceNode::factory()->create([
            'zone_id' => null,
            'status' => 'online',
        ]);

        $nodeIds = ZoneAccessHelper::getAccessibleNodeIds($user);

        $this->assertContains($unassignedNode->id, $nodeIds);
        $this->assertTrue(ZoneAccessHelper::canAccessNode($user, $unassignedNode));
    }

    public function test_greenhouse_scope_allows_agronomist_without_assignment(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();

        $this->assertTrue(ZoneAccessHelper::canAccessGreenhouseScope($user, $greenhouse));
    }

    public function test_greenhouse_scope_allows_access_via_zone_assignment_in_same_greenhouse(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $user->greenhouses()->sync([]);
        $user->zones()->sync([$zone->id]);

        $this->assertFalse(ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse));
        $this->assertTrue(ZoneAccessHelper::canAccessGreenhouseScope($user, $greenhouse));
    }
}
