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
        $this->assertEquals('active', $alert->status);
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
}

