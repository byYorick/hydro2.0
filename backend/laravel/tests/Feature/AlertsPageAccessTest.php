<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\Concerns\InteractsWithViews;
use Inertia\Testing\AssertableInertia;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertsPageAccessTest extends TestCase
{
    use RefreshDatabase;
    use InteractsWithViews;

    public function test_alerts_page_includes_global_and_accessible_zone_alerts_only(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $allowedZone = Zone::factory()->create(['name' => 'Allowed Zone']);
        $forbiddenZone = Zone::factory()->create(['name' => 'Forbidden Zone']);

        $user->zones()->attach($allowedZone->id);

        $globalAlert = Alert::factory()->create([
            'zone_id' => null,
            'message' => 'Global alert',
        ]);
        $allowedAlert = Alert::factory()->create([
            'zone_id' => $allowedZone->id,
            'message' => 'Allowed alert',
        ]);
        $forbiddenAlert = Alert::factory()->create([
            'zone_id' => $forbiddenZone->id,
            'message' => 'Forbidden alert',
        ]);

        $this->actingAs($user)
            ->get('/alerts')
            ->assertOk()
            ->assertInertia(function (AssertableInertia $page) use ($globalAlert, $allowedAlert, $forbiddenAlert, $allowedZone): void {
                $page->component('Alerts/Index')
                    ->has('alerts', 2)
                    ->where('alerts.0.id', $allowedAlert->id)
                    ->where('alerts.1.id', $globalAlert->id)
                    ->has('zones', 1)
                    ->where('zones.0.id', $allowedZone->id);

                $alertIds = collect($page->toArray()['props']['alerts'] ?? [])->pluck('id')->all();
                $this->assertContains($globalAlert->id, $alertIds);
                $this->assertContains($allowedAlert->id, $alertIds);
                $this->assertNotContains($forbiddenAlert->id, $alertIds);
            });
    }
}
