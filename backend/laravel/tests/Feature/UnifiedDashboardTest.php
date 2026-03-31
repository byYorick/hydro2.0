<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use Tests\TestCase;

class UnifiedDashboardTest extends TestCase
{
    use RefreshDatabase;

    public function test_dashboard_renders_unified_inertia_props(): void
    {
        $user = User::factory()->create([
            'role' => 'admin',
        ]);

        $response = $this->actingAs($user)->get('/');

        $response->assertOk();
        $response->assertInertia(function (AssertableInertia $page): void {
            $page->component('Dashboard/Index')
                ->has('summary')
                ->has('zones')
                ->has('greenhouses')
                ->has('latestAlerts')
                ->where('summary.zones_total', fn ($v) => is_int($v))
                ->where('summary.zones_running', fn ($v) => is_int($v))
                ->where('summary.zones_warning', fn ($v) => is_int($v))
                ->where('summary.zones_alarm', fn ($v) => is_int($v))
                ->where('summary.cycles_running', fn ($v) => is_int($v))
                ->where('summary.greenhouses_count', fn ($v) => is_int($v));
        });
    }

    public function test_cycles_url_redirects_to_dashboard(): void
    {
        $user = User::factory()->create([
            'role' => 'viewer',
        ]);

        $this->actingAs($user)
            ->get('/cycles')
            ->assertRedirect('/');
    }

    public function test_cycles_route_name_still_registered(): void
    {
        $this->assertTrue(\Illuminate\Support\Facades\Route::has('cycles.center'));
    }

    public function test_dashboard_normalizes_ec_units_for_gauge(): void
    {
        $user = User::factory()->create([
            'role' => 'admin',
        ]);

        $zone = \App\Models\Zone::factory()->create([
            'status' => 'RUNNING',
        ]);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
        ]);

        $ecSensor = Sensor::factory()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'type' => 'EC',
            'label' => 'ec_sensor',
            'is_active' => true,
        ]);

        // EC в µS/см (например 1200) должен стать 1.2 мСм/см для UI.
        TelemetryLast::query()->create([
            'sensor_id' => $ecSensor->id,
            'last_value' => 1200,
            'last_ts' => now()->subMinute(),
            'last_quality' => 'GOOD',
        ]);

        $response = $this->actingAs($user)->get('/');

        $response->assertOk();
        $response->assertInertia(function (AssertableInertia $page) use ($zone): void {
            $page->component('Dashboard/Index')
                ->has('zones')
                ->where('zones.0.id', $zone->id)
                ->where('zones.0.telemetry.ec', 1.2);
        });
    }
}
