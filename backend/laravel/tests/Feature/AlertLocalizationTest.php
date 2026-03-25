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

    public function test_alerts_api_returns_expanded_message_for_ae3_task_failed(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        Alert::query()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_ae3_task_failed',
            'type' => 'Ошибка задачи автоматики',
            'status' => 'ACTIVE',
            'category' => 'operations',
            'severity' => 'error',
            'details' => [
                'task_id' => 77,
                'task_type' => 'cycle_start',
                'stage' => 'tank_recirc',
                'workflow_phase' => 'ready',
                'topology' => 'two_tank',
                'stage_retry_count' => 1,
                'error_code' => 'ae3_task_execution_timeout',
                'error_message' => 'Task execution exceeded runtime timeout',
                'message' => 'Task execution exceeded runtime timeout',
            ],
            'error_count' => 1,
            'first_seen_at' => now(),
            'last_seen_at' => now(),
            'created_at' => now(),
        ]);

        $this->actingAs($user)
            ->getJson("/api/alerts?zone_id={$zone->id}")
            ->assertOk()
            ->assertJsonPath('data.data.0.code', 'biz_ae3_task_failed')
            ->assertJsonPath('data.data.0.title', 'Ошибка задачи автоматики')
            ->assertJsonPath(
                'data.data.0.message',
                'Задача AE3 #77 (cycle_start) завершилась с ошибкой (код: ae3_task_execution_timeout): этап tank_recirc, workflow ready, topology two_tank, retry 1. Причина: Выполнение задачи превысило допустимый runtime timeout.'
            );
    }

    public function test_alerts_api_returns_enriched_message_for_ae3_command_timeout_with_startup_probe_context(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        Alert::query()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_ae3_task_failed',
            'type' => 'Ошибка задачи автоматики',
            'status' => 'ACTIVE',
            'category' => 'operations',
            'severity' => 'error',
            'details' => [
                'task_id' => 1,
                'task_type' => 'cycle_start',
                'stage' => 'startup',
                'workflow_phase' => 'idle',
                'topology' => 'two_tank_drip_substrate_trays',
                'stage_retry_count' => 0,
                'error_code' => 'command_timeout',
                'error_message' => 'TIMEOUT',
                'message' => 'TIMEOUT',
                'timed_out_command' => [
                    'probe_name' => 'irr_state_probe',
                    'cmd_id' => 'ae3-t1-z1-s1',
                    'node_uid' => 'nd-test-irrig-1',
                    'channel' => 'storage_state',
                    'node_status' => 'online',
                    'node_last_seen_age_sec' => 182,
                    'node_stale_online_candidate' => true,
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
            ->assertJsonPath(
                'data.data.0.message',
                'Задача AE3 #1 (cycle_start) завершилась с ошибкой (код: command_timeout): этап startup, workflow idle, topology two_tank_drip_substrate_trays. Причина: Не дождались ответа: probe irr_state_probe, команда ae3-t1-z1-s1, нода nd-test-irrig-1, канал storage_state. Контекст: статус узла online, last_seen 182 с назад, online-статус уже выглядел устаревшим.'
            );
    }
}
