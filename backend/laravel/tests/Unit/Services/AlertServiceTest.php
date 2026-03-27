<?php

namespace Tests\Unit\Services;

use App\Models\Alert;
use App\Services\AlertService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertServiceTest extends TestCase
{
    use RefreshDatabase;

    private AlertService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new AlertService();
    }

    public function test_create_alert(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $data = [
            'zone_id' => $zone->id,
            'type' => 'ph_high',
            'status' => 'active',
            'details' => ['message' => 'pH too high'],
            'created_at' => now(),
        ];

        $alert = $this->service->create($data);

        $this->assertInstanceOf(Alert::class, $alert);
        $this->assertEquals('ph_high', $alert->type);
        $this->assertEquals('ACTIVE', $alert->status);
        $this->assertDatabaseHas('alerts', [
            'id' => $alert->id,
            'type' => 'ph_high',
        ]);
    }

    public function test_acknowledge_alert(): void
    {
        $alert = Alert::factory()->create(['status' => 'active']);

        $acknowledged = $this->service->acknowledge($alert, [
            'resolved_by' => 'unit_test',
            'resolved_via' => 'manual',
            'resolved_by_user_id' => 99,
        ]);

        $this->assertEquals('RESOLVED', $acknowledged->status);
        $this->assertNotNull($acknowledged->resolved_at);
        $this->assertEquals('unit_test', $acknowledged->details['resolved_by'] ?? null);
        $this->assertEquals('manual', $acknowledged->details['resolved_via'] ?? null);
        $this->assertEquals(99, $acknowledged->details['resolved_by_user_id'] ?? null);
        $this->assertDatabaseHas('alerts', [
            'id' => $alert->id,
            'status' => 'RESOLVED',
        ]);
    }

    public function test_acknowledge_already_resolved_alert_throws_exception(): void
    {
        $alert = Alert::factory()->create(['status' => 'resolved']);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Alert is already resolved');

        $this->service->acknowledge($alert);
    }

    public function test_resolve_by_code_resolves_active_alert(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'infra_test_resolve',
            'status' => 'ACTIVE',
            'details' => ['message' => 'initial'],
        ]);

        $result = $this->service->resolveByCode($zone->id, 'infra_test_resolve', [
            'details' => ['reason' => 'recovered'],
            'resolved_by' => 'python_ingest',
            'resolved_via' => 'auto',
            'resolved_source' => 'infra',
        ]);

        $this->assertTrue($result['resolved']);
        $this->assertNotNull($result['alert']);

        $alert->refresh();
        $this->assertEquals('RESOLVED', $alert->status);
        $this->assertNotNull($alert->resolved_at);
        $this->assertEquals('recovered', $alert->details['reason'] ?? null);
        $this->assertEquals('python_ingest', $alert->details['resolved_by'] ?? null);
        $this->assertEquals('auto', $alert->details['resolved_via'] ?? null);
        $this->assertEquals('infra', $alert->details['resolved_source'] ?? null);
    }

    public function test_resolve_by_code_returns_false_when_no_active_alert(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $result = $this->service->resolveByCode($zone->id, 'infra_missing');

        $this->assertFalse($result['resolved']);
        $this->assertNull($result['alert']);
        $this->assertNull($result['event_id']);
    }

    public function test_create_or_update_active_uses_dedupe_key_for_same_code(): void
    {
        $zone = \App\Models\Zone::factory()->create();

        $first = $this->service->createOrUpdateActive([
            'zone_id' => $zone->id,
            'source' => 'infra',
            'code' => 'infra_telemetry_node_unassigned',
            'type' => 'Telemetry Anomaly',
            'node_uid' => 'nd-test-light-1',
            'details' => [
                'message' => 'Light node is unassigned',
                'dedupe_key' => 'infra_telemetry_node_unassigned|1|history-logger|telemetry_processing|nd-test-light-1|light_level|unknown_cmd|unknown_error_type',
                'sample_channel' => 'light_level',
            ],
        ]);

        $second = $this->service->createOrUpdateActive([
            'zone_id' => $zone->id,
            'source' => 'infra',
            'code' => 'infra_telemetry_node_unassigned',
            'type' => 'Telemetry Anomaly',
            'node_uid' => 'nd-test-climate-1',
            'details' => [
                'message' => 'Climate node is unassigned',
                'dedupe_key' => 'infra_telemetry_node_unassigned|1|history-logger|telemetry_processing|nd-test-climate-1|air_temp_c|unknown_cmd|unknown_error_type',
                'sample_channel' => 'air_temp_c',
            ],
        ]);

        $this->assertTrue($first['created']);
        $this->assertTrue($second['created']);
        $this->assertNotSame($first['alert']?->id, $second['alert']?->id);
        $this->assertDatabaseCount('alerts', 2);
    }

    public function test_resolve_by_code_prefers_matching_dedupe_key(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $lightDedupeKey = 'infra_telemetry_node_unassigned|1|history-logger|telemetry_processing|nd-test-light-1|light_level|unknown_cmd|unknown_error_type';
        $climateDedupeKey = 'infra_telemetry_node_unassigned|1|history-logger|telemetry_processing|nd-test-climate-1|air_temp_c|unknown_cmd|unknown_error_type';

        $lightAlert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'infra_telemetry_node_unassigned',
            'status' => 'ACTIVE',
            'node_uid' => 'nd-test-light-1',
            'details' => [
                'message' => 'Light node is unassigned',
                'dedupe_key' => $lightDedupeKey,
                'sample_channel' => 'light_level',
            ],
        ]);

        $climateAlert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'infra_telemetry_node_unassigned',
            'status' => 'ACTIVE',
            'node_uid' => 'nd-test-climate-1',
            'details' => [
                'message' => 'Climate node is unassigned',
                'dedupe_key' => $climateDedupeKey,
                'sample_channel' => 'air_temp_c',
            ],
        ]);

        $result = $this->service->resolveByCode($zone->id, 'infra_telemetry_node_unassigned', [
            'details' => [
                'dedupe_key' => $lightDedupeKey,
                'sample_channel' => 'light_level',
            ],
            'resolved_by' => 'python_ingest',
            'resolved_via' => 'auto',
            'resolved_source' => 'infra',
        ]);

        $this->assertTrue($result['resolved']);

        $lightAlert->refresh();
        $climateAlert->refresh();

        $this->assertSame('RESOLVED', $lightAlert->status);
        $this->assertSame('ACTIVE', $climateAlert->status);
    }
}
