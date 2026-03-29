<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\DatabaseTransactions;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class ZoneShowAccessTest extends TestCase
{
    use DatabaseTransactions;

    public function test_zone_show_forbidden_without_zone_assignment(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $this->revokeZoneAccess($user, $zone);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertStatus(403);
    }

    public function test_zone_show_allowed_with_greenhouse_assignment(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        DB::table('user_greenhouses')->where('user_id', $user->id)->delete();
        DB::table('user_zones')->where('user_id', $user->id)->delete();
        $user->greenhouses()->syncWithoutDetaching([$zone->greenhouse_id]);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertOk();
    }

    public function test_zones_index_hides_unassigned_zones_for_non_admin(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $allowedZone = Zone::factory()->create();
        $blockedZone = Zone::factory()->create();
        DB::table('user_greenhouses')->where('user_id', $user->id)->delete();
        DB::table('user_zones')->where('user_id', $user->id)->delete();
        $user->zones()->syncWithoutDetaching([$allowedZone->id]);

        $this->actingAs($user)
            ->get('/zones')
            ->assertOk()
            ->assertInertia(fn (\Inertia\Testing\AssertableInertia $page) => $page
                ->component('Zones/Index')
                ->has('zones', 1)
                ->where('zones.0.id', $allowedZone->id)
            );
    }

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
}
