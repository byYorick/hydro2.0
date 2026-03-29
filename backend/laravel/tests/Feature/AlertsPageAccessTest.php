<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\Concerns\InteractsWithViews;
use Illuminate\Support\Facades\DB;
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

        DB::table('user_zones')->where('user_id', $user->id)->delete();
        DB::table('user_greenhouses')->where('user_id', $user->id)->delete();
        $user->zones()->syncWithoutDetaching([$allowedZone->id]);

        $globalAlert = Alert::factory()->create([
            'zone_id' => null,
            'details' => ['message' => 'Global alert'],
        ]);
        $allowedAlert = Alert::factory()->create([
            'zone_id' => $allowedZone->id,
            'details' => ['message' => 'Allowed alert'],
        ]);
        $forbiddenAlert = Alert::factory()->create([
            'zone_id' => $forbiddenZone->id,
            'details' => ['message' => 'Forbidden alert'],
        ]);

        $this->actingAs($user)
            ->get('/alerts')
            ->assertOk()
            ->assertInertia(function (AssertableInertia $page) use ($globalAlert, $allowedAlert, $forbiddenAlert, $allowedZone): void {
                $alertIds = collect($page->toArray()['props']['alerts'] ?? [])->pluck('id')->all();
                $zoneIds = collect($page->toArray()['props']['zones'] ?? [])->pluck('id')->all();

                $page->component('Alerts/Index');
                $this->assertContains($globalAlert->id, $alertIds);
                $this->assertContains($allowedAlert->id, $alertIds);
                $this->assertNotContains($forbiddenAlert->id, $alertIds);
                $this->assertContains($allowedZone->id, $zoneIds);
            });
    }
}
