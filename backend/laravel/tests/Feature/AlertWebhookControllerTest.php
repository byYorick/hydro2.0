<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertWebhookControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_webhook_creates_alert_on_firing(): void
    {
        $zone = Zone::factory()->create();

        $payload = [
            'alerts' => [
                [
                    'status' => 'firing',
                    'labels' => [
                        'alertname' => 'NodeOffline',
                        'severity' => 'critical',
                        'zone_id' => (string) $zone->id,
                    ],
                    'annotations' => [
                        'summary' => 'Node is offline',
                        'description' => 'Node has been offline for more than 5 minutes',
                    ],
                    'startsAt' => now()->toIso8601String(),
                ],
            ],
        ];

        $response = $this->postJson('/api/alerts/webhook', $payload);

        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);

        $this->assertDatabaseHas('alerts', [
            'zone_id' => $zone->id,
            'type' => 'NodeOffline',
            'status' => 'ACTIVE',
        ]);
    }

    public function test_webhook_resolves_alert_on_resolved(): void
    {
        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'NodeOffline',
            'status' => 'ACTIVE',
        ]);

        $payload = [
            'alerts' => [
                [
                    'status' => 'resolved',
                    'labels' => [
                        'alertname' => 'NodeOffline',
                        'zone_id' => (string) $zone->id,
                    ],
                    'annotations' => [],
                ],
            ],
        ];

        $response = $this->postJson('/api/alerts/webhook', $payload);

        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);

        $this->assertDatabaseHas('alerts', [
            'id' => $alert->id,
            'status' => 'RESOLVED',
        ]);
    }

    public function test_webhook_handles_empty_alerts_array(): void
    {
        $payload = ['alerts' => []];

        $response = $this->postJson('/api/alerts/webhook', $payload);

        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);
    }

    public function test_webhook_handles_missing_alerts_key(): void
    {
        $payload = [];

        $response = $this->postJson('/api/alerts/webhook', $payload);

        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);
    }
}

