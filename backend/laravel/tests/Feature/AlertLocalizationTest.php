<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertLocalizationTest extends TestCase
{
    use RefreshDatabase;

    public function test_alerts_api_returns_localized_message_for_zone_correction_config_missing(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        Alert::query()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_zone_correction_config_missing',
            'type' => 'automation_engine',
            'status' => 'ACTIVE',
            'category' => 'config',
            'severity' => 'critical',
            'details' => [
                'message' => 'Zone 1 correction_config.base missing required fields: runtime, timing, dosing, retry, tolerance, controllers, safety; fail-closed for critical correction parameters',
            ],
            'error_count' => 1,
            'first_seen_at' => now(),
            'last_seen_at' => now(),
            'created_at' => now(),
        ]);

        $this->actingAs($user)
            ->getJson("/api/alerts?zone_id={$zone->id}")
            ->assertOk()
            ->assertJsonPath('data.data.0.code', 'biz_zone_correction_config_missing')
            ->assertJsonPath('data.data.0.title', 'Не настроен correction config зоны')
            ->assertJsonPath(
                'data.data.0.message',
                'В зоне 1 в correction_config.base отсутствуют обязательные поля: runtime, timing, dosing, retry, tolerance, controllers, safety; критические параметры коррекции переведены в fail-closed режим.'
            );
    }

    public function test_alerts_api_returns_localized_message_for_alertmanager_alertname(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        Alert::query()->create([
            'zone_id' => $zone->id,
            'source' => 'infra',
            'code' => 'unknown_alert',
            'type' => 'NodeOffline',
            'status' => 'ACTIVE',
            'category' => 'infrastructure',
            'severity' => 'critical',
            'details' => [
                'labels' => [
                    'alertname' => 'NodeOffline',
                    'uid' => 'node-ph-1',
                ],
            ],
            'error_count' => 1,
            'first_seen_at' => now(),
            'last_seen_at' => now(),
            'created_at' => now(),
        ]);

        $this->actingAs($user)
            ->getJson("/api/alerts?zone_id={$zone->id}")
            ->assertOk()
            ->assertJsonPath('data.data.0.type', 'NodeOffline')
            ->assertJsonPath('data.data.0.title', 'Узел офлайн')
            ->assertJsonPath('data.data.0.message', 'Узел офлайн');
    }
}
