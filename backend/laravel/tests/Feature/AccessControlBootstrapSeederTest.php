<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Database\Seeders\AccessControlBootstrapSeeder;
use Illuminate\Foundation\Testing\DatabaseTransactions;
use Tests\TestCase;

class AccessControlBootstrapSeederTest extends TestCase
{
    use DatabaseTransactions;

    public function test_bootstrap_seeder_assigns_existing_non_admin_users_to_current_topology(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $viewer = User::factory()->create(['role' => 'viewer']);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $this->seed(AccessControlBootstrapSeeder::class);

        $this->assertDatabaseHas('user_greenhouses', [
            'user_id' => $viewer->id,
            'greenhouse_id' => $greenhouse->id,
        ]);
        $this->assertDatabaseHas('user_zones', [
            'user_id' => $viewer->id,
            'zone_id' => $zone->id,
        ]);

        $this->assertDatabaseMissing('user_greenhouses', [
            'user_id' => $admin->id,
            'greenhouse_id' => $greenhouse->id,
        ]);
        $this->assertDatabaseMissing('user_zones', [
            'user_id' => $admin->id,
            'zone_id' => $zone->id,
        ]);
    }
}
