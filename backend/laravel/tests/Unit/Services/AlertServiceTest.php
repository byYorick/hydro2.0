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

        $acknowledged = $this->service->acknowledge($alert);

        $this->assertEquals('RESOLVED', $acknowledged->status);
        $this->assertNotNull($acknowledged->resolved_at);
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
        ]);

        $this->assertTrue($result['resolved']);
        $this->assertNotNull($result['alert']);

        $alert->refresh();
        $this->assertEquals('RESOLVED', $alert->status);
        $this->assertNotNull($alert->resolved_at);
        $this->assertEquals('recovered', $alert->details['reason'] ?? null);
    }

    public function test_resolve_by_code_returns_false_when_no_active_alert(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $result = $this->service->resolveByCode($zone->id, 'infra_missing');

        $this->assertFalse($result['resolved']);
        $this->assertNull($result['alert']);
        $this->assertNull($result['event_id']);
    }
}
