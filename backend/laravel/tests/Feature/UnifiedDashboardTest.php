<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\DeviceNode;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Inertia\Testing\AssertableInertia;
use Tests\TestCase;

class UnifiedDashboardTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Cache::flush();
    }

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

    public function test_dashboard_marks_zone_as_blocked_by_policy_managed_alert(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_ae3_task_failed',
            'type' => 'AE3_TASK_FAILED',
            'status' => 'ACTIVE',
            'severity' => 'critical',
            'details' => [
                'human_error_message' => 'Цикл прерван: prepare_recirculation timeout',
                'task_id' => 42,
            ],
            'created_at' => now()->subMinutes(5),
        ]);

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_ph_correction_no_effect',
            'type' => 'PH_NO_EFFECT',
            'status' => 'ACTIVE',
            'severity' => 'warning',
            'details' => ['message' => 'pH дозы не дают эффекта'],
            'created_at' => now()->subMinutes(2),
        ]);

        $response = $this->actingAs($user)->get('/');

        $response->assertOk();
        $response->assertInertia(function (AssertableInertia $page) use ($zone): void {
            $page->component('Dashboard/Index')
                ->where('summary.zones_blocked', 1)
                ->where('zones', function ($zones) use ($zone): bool {
                    $zonePayload = collect($zones)->firstWhere('id', $zone->id);

                    return is_array($zonePayload)
                        && data_get($zonePayload, 'automation_block.blocked') === true
                        && data_get($zonePayload, 'automation_block.reason_code') === 'biz_ae3_task_failed'
                        && data_get($zonePayload, 'automation_block.severity') === 'critical'
                        && data_get($zonePayload, 'automation_block.message') === 'Цикл прерван: prepare_recirculation timeout'
                        && data_get($zonePayload, 'automation_block.alerts_count') === 2;
                });
        });
    }

    public function test_dashboard_marks_zone_as_blocked_for_uppercase_policy_code(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'BIZ_AE3_TASK_FAILED',
            'type' => 'AE3_TASK_FAILED',
            'status' => 'ACTIVE',
            'severity' => 'critical',
            'details' => ['human_error_message' => 'Ошибка в верхнем регистре'],
            'created_at' => now()->subMinutes(1),
        ]);

        $response = $this->actingAs($user)->get('/');

        $response->assertOk();
        $response->assertInertia(function (AssertableInertia $page) use ($zone): void {
            $page->component('Dashboard/Index')
                ->where('summary.zones_blocked', 1)
                ->where('zones', function ($zones) use ($zone): bool {
                    $zonePayload = collect($zones)->firstWhere('id', $zone->id);

                    return is_array($zonePayload)
                        && data_get($zonePayload, 'automation_block.blocked') === true
                        && data_get($zonePayload, 'automation_block.reason_code') === 'BIZ_AE3_TASK_FAILED';
                });
        });
    }

    public function test_dashboard_drops_block_after_resolving_alert_via_alert_service(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_ae3_task_failed',
            'type' => 'AE3_TASK_FAILED',
            'status' => 'ACTIVE',
            'severity' => 'critical',
            'details' => ['human_error_message' => 'X'],
            'created_at' => now()->subMinute(),
        ]);

        // Первая выдача — кэш заполнен, зона помечена как blocked.
        $this->actingAs($user)->get('/')->assertOk()
            ->assertInertia(fn (AssertableInertia $p) => $p
                ->component('Dashboard/Index')
                ->where('summary.zones_blocked', 1)
                ->etc()
            );

        // Резолвим алерт штатно через сервис — он должен сбросить кэш дашборда.
        /** @var \App\Services\AlertService $service */
        $service = app(\App\Services\AlertService::class);
        $service->resolveByCode($zone->id, 'biz_ae3_task_failed', [
            'resolved_via' => 'manual',
            'resolved_by' => 'tester',
        ]);

        // Вторая выдача — кэш сброшен, automation_block снят, zones_blocked = 0.
        $this->actingAs($user)->get('/')->assertOk()
            ->assertInertia(function (AssertableInertia $page) use ($zone): void {
                $page->component('Dashboard/Index')
                    ->where('summary.zones_blocked', 0)
                    ->where('zones', function ($zones) use ($zone): bool {
                        $zonePayload = collect($zones)->firstWhere('id', $zone->id);

                        return is_array($zonePayload)
                            && data_get($zonePayload, 'automation_block') === null;
                    });
            });
    }

    public function test_dashboard_does_not_mark_zone_as_blocked_for_non_policy_alerts(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'infra',
            'code' => 'infra_command_timeout',
            'type' => 'COMMAND_TIMEOUT',
            'status' => 'ACTIVE',
            'severity' => 'error',
            'details' => ['message' => 'taimeout'],
            'created_at' => now()->subMinute(),
        ]);

        $response = $this->actingAs($user)->get('/');

        $response->assertOk();
        $response->assertInertia(function (AssertableInertia $page) use ($zone): void {
            $page->component('Dashboard/Index')
                ->where('summary.zones_blocked', 0)
                ->where('zones', function ($zones) use ($zone): bool {
                    $zonePayload = collect($zones)->firstWhere('id', $zone->id);

                    return is_array($zonePayload)
                        && data_get($zonePayload, 'automation_block') === null;
                });
        });
    }

    public function test_dashboard_alerts_preview_carries_code_and_severity(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_zone_correction_config_missing',
            'type' => 'CONFIG_MISSING',
            'status' => 'ACTIVE',
            'severity' => 'error',
            'details' => ['message' => 'нет конфига'],
            'created_at' => now()->subMinute(),
        ]);

        $response = $this->actingAs($user)->get('/');

        $response->assertOk();
        $response->assertInertia(function (AssertableInertia $page) use ($zone): void {
            $page->component('Dashboard/Index')
                ->where('zones', function ($zones) use ($zone): bool {
                    $zonePayload = collect($zones)->firstWhere('id', $zone->id);
                    if (! is_array($zonePayload)) {
                        return false;
                    }

                    $alertsPreview = collect(data_get($zonePayload, 'alerts_preview', []));
                    /** @var array<string, mixed>|null $alert */
                    $alert = $alertsPreview->first(function (mixed $item): bool {
                        return is_array($item)
                            && ($item['code'] ?? null) === 'biz_zone_correction_config_missing';
                    });

                    return is_array($alert)
                        && ($alert['severity'] ?? null) === 'error'
                        && ($alert['source'] ?? null) === 'biz';
                });
        });
    }
}
