<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertWebhookControllerTest extends TestCase
{
    use RefreshDatabase;

    private const WEBHOOK_SECRET = 'test-alertmanager-webhook-secret';

    protected function setUp(): void
    {
        parent::setUp();

        config(['services.alertmanager.webhook_secret' => self::WEBHOOK_SECRET]);
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function postWebhook(array $payload): \Illuminate\Testing\TestResponse
    {
        return $this->withHeaders(['X-Webhook-Secret' => self::WEBHOOK_SECRET])
            ->postJson('/api/alerts/webhook', $payload);
    }

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

        $response = $this->postWebhook($payload);

        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);

        $this->assertDatabaseHas('alerts', [
            'zone_id' => $zone->id,
            'type' => 'NodeOffline',
            'status' => 'ACTIVE',
        ]);
    }

    public function test_webhook_rejects_request_without_secret(): void
    {
        $this->postJson('/api/alerts/webhook', ['alerts' => []])
            ->assertStatus(401);
    }

    public function test_webhook_accepts_bearer_token(): void
    {
        $this->withHeaders(['Authorization' => 'Bearer '.self::WEBHOOK_SECRET])
            ->postJson('/api/alerts/webhook', ['alerts' => []])
            ->assertOk()
            ->assertJson(['status' => 'ok']);
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

        $response = $this->postWebhook($payload);

        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);

        $this->assertDatabaseHas('alerts', [
            'id' => $alert->id,
            'status' => 'RESOLVED',
        ]);

        $alert->refresh();
        $this->assertSame('alertmanager_webhook', $alert->details['resolved_by'] ?? null);
        $this->assertSame('auto', $alert->details['resolved_via'] ?? null);
        $this->assertSame('alertmanager', $alert->details['resolved_source'] ?? null);
    }

    public function test_webhook_handles_empty_alerts_array(): void
    {
        $payload = ['alerts' => []];

        $response = $this->postWebhook($payload);

        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);
    }

    public function test_webhook_handles_missing_alerts_key(): void
    {
        $payload = [];

        $response = $this->postWebhook($payload);

        $response->assertStatus(200);
        $response->assertJson(['status' => 'ok']);
    }
}
