<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use App\Services\GreenhouseClimate\GreenhouseClimateDispatchService;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Laravel\Sanctum\Sanctum;
use Tests\RefreshDatabase;
use Tests\TestCase;

class GreenhouseClimateApiTest extends TestCase
{
    use RefreshDatabase;

    private function grantZoneAccess(User $user, Zone $zone): void
    {
        // GreenhouseObserver назначает новую теплицу всем не-admin пользователям (user_greenhouses).
        // Для этих тестов нужен строгий ACL только через user_zones.
        DB::table('user_greenhouses')->where('user_id', $user->id)->delete();
        DB::table('user_zones')->insertOrIgnore([
            'user_id' => $user->id,
            'zone_id' => $zone->id,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
    }

    public function test_state_endpoint_creates_automation_state_row(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $this->grantZoneAccess($user, $zone);
        Sanctum::actingAs($user);

        $response = $this->getJson('/api/greenhouses/'.$greenhouse->id.'/climate/state');
        $response->assertOk();
        $response->assertJsonPath('data.state.greenhouse_id', $greenhouse->id);
        $this->assertDatabaseHas('greenhouse_automation_state', [
            'greenhouse_id' => $greenhouse->id,
        ]);
    }

    public function test_state_returns_403_when_user_has_no_access_to_greenhouse(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $allowed = Greenhouse::factory()->create();
        $denied = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $allowed->id]);
        $this->grantZoneAccess($user, $zone);
        Sanctum::actingAs($user);

        $response = $this->getJson('/api/greenhouses/'.$denied->id.'/climate/state');
        $response->assertForbidden();
    }

    public function test_control_mode_updates_state(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $this->grantZoneAccess($user, $zone);
        Sanctum::actingAs($user);

        $response = $this->postJson('/api/greenhouses/'.$greenhouse->id.'/climate/control-mode', [
            'control_mode' => 'semi',
        ]);
        $response->assertOk();
        $response->assertJsonPath('data.control_mode', 'semi');
        $this->assertDatabaseHas('greenhouse_automation_state', [
            'greenhouse_id' => $greenhouse->id,
            'control_mode' => 'semi',
        ]);
    }

    public function test_control_mode_validation_rejects_invalid_mode(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $this->grantZoneAccess($user, $zone);
        Sanctum::actingAs($user);

        $response = $this->postJson('/api/greenhouses/'.$greenhouse->id.'/climate/control-mode', [
            'control_mode' => 'turbo',
        ]);
        $response->assertUnprocessable();
        $response->assertJsonValidationErrors(['control_mode']);
    }

    public function test_manual_override_ttl_validation(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $this->grantZoneAccess($user, $zone);
        Sanctum::actingAs($user);

        $tooLow = $this->postJson('/api/greenhouses/'.$greenhouse->id.'/climate/manual-override', [
            'left_position_pct' => 10,
            'right_position_pct' => 20,
            'ttl_sec' => 59,
            'return_mode' => 'auto',
        ]);
        $tooLow->assertUnprocessable();
        $tooLow->assertJsonValidationErrors(['ttl_sec']);

        $tooHigh = $this->postJson('/api/greenhouses/'.$greenhouse->id.'/climate/manual-override', [
            'left_position_pct' => 10,
            'right_position_pct' => 20,
            'ttl_sec' => 86401,
            'return_mode' => 'auto',
        ]);
        $tooHigh->assertUnprocessable();
        $tooHigh->assertJsonValidationErrors(['ttl_sec']);
    }

    public function test_manual_override_store_and_delete(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $this->grantZoneAccess($user, $zone);
        Sanctum::actingAs($user);

        $store = $this->postJson('/api/greenhouses/'.$greenhouse->id.'/climate/manual-override', [
            'left_position_pct' => 15,
            'right_position_pct' => 25,
            'ttl_sec' => 120,
            'return_mode' => 'semi',
            'reason' => 'test override',
        ]);
        $store->assertOk();
        $store->assertJsonPath('status', 'ok');
        $this->assertDatabaseHas('greenhouse_manual_overrides', [
            'greenhouse_id' => $greenhouse->id,
            'left_position_pct' => 15,
            'right_position_pct' => 25,
        ]);

        $del = $this->deleteJson('/api/greenhouses/'.$greenhouse->id.'/climate/manual-override');
        $del->assertOk();
        $this->assertSame(0, DB::table('greenhouse_manual_overrides')->where('greenhouse_id', $greenhouse->id)->count());
    }

    public function test_viewer_cannot_post_control_mode(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $this->grantZoneAccess($user, $zone);
        Sanctum::actingAs($user);

        $response = $this->postJson('/api/greenhouses/'.$greenhouse->id.'/climate/control-mode', [
            'control_mode' => 'auto',
        ]);
        $response->assertForbidden();
    }

    public function test_dispatch_reuses_pending_intent_when_waking_automation_engine(): void
    {
        config([
            'services.automation_engine.api_url' => 'http://automation-engine:9405',
            'services.automation_engine.scheduler_api_token' => 'test-token',
            'services.automation_engine.timeout' => 0.5,
        ]);
        Http::fake([
            'automation-engine:9405/*' => Http::response(['status' => 'accepted'], 202),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        DB::table('greenhouse_automation_state')->insert([
            'greenhouse_id' => $greenhouse->id,
            'control_mode' => 'auto',
            'next_scheduled_tick_at' => now()->subMinute(),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $service = app(GreenhouseClimateDispatchService::class);
        $service->dispatchDue();
        $firstIntent = DB::table('greenhouse_automation_intents')
            ->where('greenhouse_id', $greenhouse->id)
            ->first();

        $this->assertNotNull($firstIntent);

        $service->dispatchDue();

        $this->assertSame(1, DB::table('greenhouse_automation_intents')
            ->where('greenhouse_id', $greenhouse->id)
            ->count());
        Http::assertSentCount(2);
        Http::assertSent(fn ($request) => $request->url() === 'http://automation-engine:9405/greenhouses/'.$greenhouse->id.'/start-climate-tick'
            && $request['idempotency_key'] === $firstIntent->idempotency_key);
    }
}
