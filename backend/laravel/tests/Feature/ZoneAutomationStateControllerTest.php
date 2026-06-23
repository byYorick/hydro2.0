<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationStateControllerTest extends TestCase
{
    use RefreshDatabase;

    private function automationEngineUrl(): string
    {
        return rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
    }

    private function seedActivePolicyManagedAlert(Zone $zone): void
    {
        Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_ae3_task_failed',
            'status' => 'ACTIVE',
        ]);
    }

    public function test_automation_state_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/state");

        $response->assertStatus(401);
    }

    public function test_automation_state_proxies_payload_from_automation_engine(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create([
            'status' => 'PAUSED',
            'water_state' => 'WATER_CHANGE_FILL',
        ]);
        $this->seedActivePolicyManagedAlert($zone);
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_FILLING',
                'state_label' => 'Набор бака с раствором',
                'state_details' => [
                    'started_at' => now()->subSeconds(45)->toIso8601String(),
                    'elapsed_sec' => 45,
                    'progress_percent' => 30,
                    'failed' => true,
                    'error_code' => 'command_timeout',
                    'error_message' => 'TIMEOUT',
                ],
                'system_config' => [
                    'tanks_count' => 2,
                    'system_type' => 'drip',
                    'clean_tank_capacity_l' => 50,
                    'nutrient_tank_capacity_l' => 100,
                ],
                'current_levels' => [
                    'clean_tank_level_percent' => 70,
                    'nutrient_tank_level_percent' => 45,
                    'ph' => 5.9,
                    'ec' => 1.4,
                ],
                'active_processes' => [
                    'pump_in' => true,
                    'circulation_pump' => false,
                    'ph_correction' => true,
                    'ec_correction' => true,
                ],
                'timeline' => [],
                'next_state' => 'TANK_RECIRC',
                'estimated_completion_sec' => 120,
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('zone_id', $zone->id)
            ->assertJsonPath('state', 'TANK_FILLING')
            ->assertJsonPath('system_config.tanks_count', 2)
            ->assertJsonPath('active_processes.pump_in', true)
            ->assertJsonPath('state_details.human_error_message', 'Не дождались подтверждения или итогового ответа по команде в допустимое время.')
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('state_meta.is_stale', false);

        $this->assertDatabaseHas('zones', [
            'id' => $zone->id,
            'status' => 'PAUSED',
            'water_state' => 'WATER_CHANGE_FILL',
        ]);
    }

    public function test_automation_state_humanizes_snapshot_error_by_canonical_code(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $this->seedActivePolicyManagedAlert($zone);
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IDLE',
                'state_label' => 'Ожидание',
                'state_details' => [
                    'failed' => true,
                    'error_code' => 'ae3_snapshot_no_online_actuator_channels',
                    'error_message' => "Zone {$zone->id} has no online actuator channels",
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('state_details.error_code', 'ae3_snapshot_no_online_actuator_channels')
            ->assertJsonPath(
                'state_details.human_error_message',
                'В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.'
            );
    }

    public function test_automation_state_humanizes_new_fail_safe_terminal_code(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $this->seedActivePolicyManagedAlert($zone);
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IDLE',
                'state_label' => 'Ожидание',
                'state_details' => [
                    'failed' => true,
                    'error_code' => 'solution_fill_leak_detected',
                    'error_message' => 'Solution minimum level dropped during solution fill',
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('state_details.error_code', 'solution_fill_leak_detected')
            ->assertJsonPath(
                'state_details.human_error_message',
                'Наполнение раствором остановлено: нижний уровень раствора пропал после guard-delay, возможна утечка или неправильная гидравлика.'
            );
    }

    public function test_automation_state_overlays_control_mode_from_zone_row(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create(['control_mode' => 'semi']);
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IDLE',
                'state_label' => 'Ожидание',
                'control_mode' => 'auto',
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('control_mode', 'semi')
            ->assertJsonPath('control_mode_available', ['auto', 'semi', 'manual']);
    }

    public function test_automation_state_returns_upstream_unavailable_on_request_exception(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'status' => 'error',
                'message' => 'temporary degradation',
            ], 500),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertStatus(503)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'upstream_unavailable');
    }

    public function test_automation_state_returns_cached_snapshot_when_upstream_is_temporarily_unavailable(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_RECIRC',
                'state_label' => 'Рециркуляция бака',
                'state_details' => [
                    'started_at' => now()->subSeconds(10)->toIso8601String(),
                    'elapsed_sec' => 10,
                    'progress_percent' => 42,
                ],
                'system_config' => [
                    'tanks_count' => 2,
                    'system_type' => 'drip',
                    'clean_tank_capacity_l' => 50,
                    'nutrient_tank_capacity_l' => 100,
                ],
                'current_levels' => [
                    'clean_tank_level_percent' => 85,
                    'nutrient_tank_level_percent' => 70,
                    'ph' => 5.9,
                    'ec' => 1.5,
                ],
                'active_processes' => [
                    'pump_in' => false,
                    'circulation_pump' => true,
                    'ph_correction' => true,
                    'ec_correction' => true,
                ],
                'timeline' => [],
                'next_state' => 'READY',
                'estimated_completion_sec' => 120,
            ], 200),
        ]);

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state")
            ->assertOk()
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('state_meta.is_stale', false);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => function () {
                throw new \RuntimeException('upstream_down');
            },
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('zone_id', $zone->id)
            ->assertJsonPath('state', 'TANK_RECIRC')
            ->assertJsonPath('state_meta.source', 'cache')
            ->assertJsonPath('state_meta.is_stale', true);
    }

    public function test_automation_state_falls_back_to_control_mode_when_state_endpoint_is_missing(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create(['control_mode' => 'semi']);
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'detail' => 'Not Found',
            ], 404),
            "{$apiUrl}/zones/{$zone->id}/control-mode" => Http::response([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'control_mode' => 'semi',
                    'workflow_phase' => 'tank_recirc',
                    'current_stage' => 'prepare_recirculation_check',
                    'allowed_manual_steps' => ['prepare_recirculation_stop'],
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('zone_id', $zone->id)
            ->assertJsonPath('state', 'TANK_RECIRC')
            ->assertJsonPath('state_label', 'Рециркуляция раствора')
            ->assertJsonPath('control_mode', 'semi')
            ->assertJsonPath('workflow_phase', 'tank_recirc')
            ->assertJsonPath('current_stage', 'prepare_recirculation_check')
            ->assertJsonPath('allowed_manual_steps.0', 'prepare_recirculation_stop')
            ->assertJsonPath('compatibility.source', 'ae3_control_mode_fallback')
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('state_meta.is_stale', false);
    }

    public function test_automation_state_does_not_mutate_zone_aggregate_on_read(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create([
            'status' => 'NEW',
            'water_state' => 'WATER_CHANGE_STABILIZE',
        ]);
        $apiUrl = $this->automationEngineUrl();

        \App\Models\GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'greenhouse_id' => $zone->greenhouse_id,
            'status' => \App\Enums\GrowCycleStatus::PLANNED,
        ]);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IDLE',
                'state_label' => 'Ожидание',
                'state_details' => [],
                'workflow_phase' => 'idle',
                'current_stage' => 'startup',
            ], 200),
        ]);

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state")
            ->assertOk()
            ->assertJsonPath('state', 'IDLE');

        $this->assertDatabaseHas('zones', [
            'id' => $zone->id,
            'status' => 'NEW',
            'water_state' => 'WATER_CHANGE_STABILIZE',
        ]);
    }

    public function test_automation_state_clears_terminal_failure_when_policy_managed_alert_is_resolved(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_ae3_task_failed',
            'status' => 'RESOLVED',
            'details' => [
                'error_code' => 'irr_state_mismatch',
                'human_error_message' => 'Состояние IRR-ноды не совпало по признаку valve_solution_supply: ожидалось=True, получено=False',
            ],
        ]);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'READY',
                'state_label' => 'Полив — сбой',
                'current_stage' => 'irrigation_check',
                'current_stage_label' => 'Полив',
                'state_details' => [
                    'failed' => true,
                    'error_code' => 'irr_state_mismatch',
                    'error_message' => 'IRR state mismatch for valve_solution_supply: expected=True, got=False',
                ],
                'workflow_phase' => 'ready',
                'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
                'current_levels' => [
                    'clean_tank_level_percent' => 50,
                    'nutrient_tank_level_percent' => 50,
                ],
                'active_processes' => [
                    'pump_in' => false,
                    'circulation_pump' => false,
                    'ph_correction' => false,
                    'ec_correction' => false,
                ],
                'timeline' => [],
            ], 200),
        ]);

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state")
            ->assertOk()
            ->assertJsonPath('state_details.failed', false)
            ->assertJsonPath('state_details.error_code', null)
            ->assertJsonPath('state_details.human_error_message', null)
            ->assertJsonPath('state_label', 'Полив');
    }

    public function test_automation_state_keeps_terminal_failure_while_policy_managed_alert_is_active(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_ae3_task_failed',
            'status' => 'ACTIVE',
        ]);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IDLE',
                'state_label' => 'Полив — сбой',
                'state_details' => [
                    'failed' => true,
                    'error_code' => 'irr_state_mismatch',
                    'error_message' => 'IRR state mismatch for valve_solution_supply: expected=True, got=False',
                ],
            ], 200),
        ]);

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state")
            ->assertOk()
            ->assertJsonPath('state_details.failed', true)
            ->assertJsonPath('state_details.error_code', 'irr_state_mismatch')
            ->assertJsonPath(
                'state_details.human_error_message',
                'Состояние IRR-ноды не совпало с ожиданиями автоматики.'
            );
    }

    public function test_automation_state_enriches_observability_from_db_when_serving_cached_snapshot(): void
    {
        Cache::flush();
        Carbon::setTestNow(Carbon::parse('2026-06-23 12:00:00'));

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();
        $now = now();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_FILLING',
                'state_label' => 'Наполнение баков',
                'workflow_phase' => 'tank_filling',
                'current_stage' => 'clean_fill_check',
                'state_details' => [
                    'started_at' => $now->copy()->subMinutes(8)->toIso8601String(),
                    'elapsed_sec' => 480,
                    'progress_percent' => 25,
                    'failed' => false,
                ],
                'system_config' => [
                    'tanks_count' => 2,
                    'system_type' => 'drip',
                    'clean_tank_capacity_l' => null,
                    'nutrient_tank_capacity_l' => null,
                ],
                'current_levels' => [
                    'clean_tank_level_percent' => 0,
                    'nutrient_tank_level_percent' => 0,
                    'ph' => null,
                    'ec' => null,
                ],
                'active_processes' => [
                    'pump_in' => true,
                    'circulation_pump' => false,
                    'ph_correction' => false,
                    'ec_correction' => false,
                ],
                'timeline' => [],
                'next_state' => null,
                'estimated_completion_sec' => null,
            ], 200),
        ]);

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state")
            ->assertOk()
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('observability.runtime.waiting_command', false);

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'waiting_command',
            'idempotency_key' => "obs-cache-test-{$zone->id}",
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'clean_fill_check',
            'workflow_phase' => 'tank_filling',
            'control_mode_snapshot' => 'auto',
            'scheduled_for' => $now,
            'due_at' => $now,
            'stage_entered_at' => $now->copy()->subMinutes(8),
            'created_at' => $now->copy()->subMinutes(8),
            'updated_at' => $now->copy()->subMinutes(3),
        ]);

        DB::table('zone_workflow_state')->updateOrInsert(
            ['zone_id' => $zone->id],
            [
                'workflow_phase' => 'tank_filling',
                'started_at' => $now->copy()->subMinutes(8),
                'updated_at' => $now->copy()->subMinutes(4),
                'payload' => json_encode([
                    'ae3_cycle_start_stage' => 'clean_fill_check',
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            ],
        );

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'cycle_start',
            'status' => 'pending',
            'idempotency_key' => "obs-cache-intent-{$zone->id}",
            'not_before' => $now->copy()->subMinutes(10),
            'created_at' => $now->copy()->subMinutes(10),
            'updated_at' => $now->copy()->subMinutes(10),
            'retry_count' => 0,
            'max_retries' => 3,
        ]);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => function () {
                throw new \RuntimeException('automation_engine_down');
            },
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('zone_id', $zone->id)
            ->assertJsonPath('state', 'TANK_FILLING')
            ->assertJsonPath('state_meta.source', 'cache')
            ->assertJsonPath('state_meta.is_stale', true)
            ->assertJsonPath('observability.runtime.task_status', 'waiting_command')
            ->assertJsonPath('observability.runtime.waiting_command', true)
            ->assertJsonPath('observability.runtime.current_stage', 'clean_fill_check')
            ->assertJsonPath('observability.scheduler.pending_count', 1);

        $hintCodes = collect($response->json('observability.hang_hints'))
            ->pluck('code')
            ->all();

        $this->assertContains('scheduler_intent_pending', $hintCodes);
        $this->assertContains('waiting_command_stuck', $hintCodes);
        $this->assertContains('stage_elapsed_long', $hintCodes);
        $this->assertContains($response->json('observability.overall_health'), ['warning', 'critical']);

        Carbon::setTestNow();
    }

    public function test_automation_state_refreshes_stale_cached_ae_observability_from_database(): void
    {
        Cache::flush();
        Carbon::setTestNow(Carbon::parse('2026-06-23 12:00:00'));

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();
        $now = now();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_FILLING',
                'state_label' => 'Набор бака с раствором',
                'workflow_phase' => 'tank_filling',
                'current_stage' => 'clean_fill_check',
                'state_details' => [
                    'started_at' => $now->copy()->subMinutes(2)->toIso8601String(),
                    'elapsed_sec' => 120,
                    'progress_percent' => 10,
                    'failed' => false,
                ],
                'observability' => [
                    'runtime' => [
                        'task_is_active' => true,
                        'task_status' => 'running',
                        'waiting_command' => false,
                        'current_stage' => 'clean_fill_check',
                        'stage_elapsed_sec' => 120,
                    ],
                    'hang_hints' => [],
                    'overall_health' => 'active',
                ],
            ], 200),
        ]);

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state")
            ->assertOk()
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('observability.runtime.task_status', 'running');

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'waiting_command',
            'idempotency_key' => "obs-stale-ae-cache-{$zone->id}",
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'clean_fill_check',
            'workflow_phase' => 'tank_filling',
            'control_mode_snapshot' => 'auto',
            'scheduled_for' => $now,
            'due_at' => $now,
            'stage_entered_at' => $now->copy()->subMinutes(8),
            'created_at' => $now->copy()->subMinutes(8),
            'updated_at' => $now->copy()->subMinutes(3),
        ]);

        DB::table('zone_workflow_state')->updateOrInsert(
            ['zone_id' => $zone->id],
            [
                'workflow_phase' => 'tank_filling',
                'started_at' => $now->copy()->subMinutes(8),
                'updated_at' => $now->copy()->subMinutes(4),
                'payload' => json_encode([
                    'ae3_cycle_start_stage' => 'clean_fill_check',
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            ],
        );

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => function () {
                throw new \RuntimeException('automation_engine_down');
            },
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('state_meta.source', 'cache')
            ->assertJsonPath('state_meta.is_stale', true)
            ->assertJsonPath('observability.runtime.task_status', 'waiting_command')
            ->assertJsonPath('observability.runtime.waiting_command', true)
            ->assertJsonPath('observability.runtime.source', 'laravel_db_fallback');

        $hintCodes = collect($response->json('observability.hang_hints'))
            ->pluck('code')
            ->all();

        $this->assertContains('waiting_command_stuck', $hintCodes);
        $this->assertContains($response->json('observability.overall_health'), ['warning', 'critical']);

        Carbon::setTestNow();
    }

    public function test_automation_state_merges_ae_observability_with_scheduler_hints(): void
    {
        Cache::flush();
        Carbon::setTestNow(Carbon::parse('2026-06-23 12:00:00'));

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'cycle_start',
            'status' => 'pending',
            'idempotency_key' => "obs-live-merge-{$zone->id}",
            'not_before' => now()->subMinutes(10),
            'created_at' => now()->subMinutes(10),
            'updated_at' => now()->subMinutes(10),
            'retry_count' => 0,
            'max_retries' => 3,
        ]);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_FILLING',
                'state_label' => 'Набор бака с раствором',
                'workflow_phase' => 'tank_filling',
                'current_stage' => 'clean_fill_check',
                'state_details' => [
                    'started_at' => now()->subMinutes(8)->toIso8601String(),
                    'elapsed_sec' => 480,
                    'progress_percent' => 20,
                    'failed' => false,
                ],
                'observability' => [
                    'runtime' => [
                        'task_is_active' => true,
                        'task_status' => 'running',
                        'current_stage' => 'clean_fill_check',
                        'stage_elapsed_sec' => 480,
                        'waiting_command' => false,
                    ],
                    'hang_hints' => [
                        [
                            'code' => 'stage_elapsed_long',
                            'severity' => 'warning',
                            'message' => 'Этап длится дольше ожидаемого',
                            'recommendation' => 'Проверьте датчики и команды узлов.',
                        ],
                    ],
                    'nodes' => ['nodes' => [], 'offline_required' => []],
                    'overall_health' => 'warning',
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('observability.scheduler.pending_count', 1);

        $hintCodes = collect($response->json('observability.hang_hints'))
            ->pluck('code')
            ->all();

        $this->assertContains('stage_elapsed_long', $hintCodes);
        $this->assertContains('scheduler_intent_pending', $hintCodes);
        $this->assertContains($response->json('observability.overall_health'), ['warning', 'critical']);

        Carbon::setTestNow();
    }
}
