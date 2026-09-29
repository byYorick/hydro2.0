<?php

namespace Tests\Unit\Services;

use App\Models\Alert;
use App\Models\Zone;
use App\Services\ZoneAutomationStateService;
use Illuminate\Http\Client\Request as HttpRequest;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationStateServiceTest extends TestCase
{
    use RefreshDatabase;

    private function automationEngineUrl(): string
    {
        return rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
    }

    private function seedActivePolicyManagedAlert(Zone $zone): void
    {
        // Без активного policy-алерта decorate очищает terminal failure — для проверки текста нужен алерт.
        Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_ae3_task_failed',
            'status' => 'ACTIVE',
        ]);
    }

    public function test_resolve_cached_bootstrap_returns_decorated_cache_without_upstream_call(): void
    {
        Cache::flush();

        $zone = Zone::factory()->create(['control_mode' => 'semi']);
        $service = app(ZoneAutomationStateService::class);

        $service->cacheState($zone->id, [
            'zone_id' => $zone->id,
            'state' => 'READY',
            'state_label' => 'Раствор готов',
            'state_details' => ['failed' => false],
            'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
            'current_levels' => [],
            'active_processes' => [],
            'timeline' => [],
        ]);

        Http::fake();

        $bootstrap = $service->resolveCachedBootstrap($zone->fresh());

        $this->assertNotNull($bootstrap);
        $this->assertSame('READY', $bootstrap['state']);
        $this->assertSame('semi', $bootstrap['control_mode']);
        $this->assertSame('cache', $bootstrap['state_meta']['source']);
        $this->assertTrue($bootstrap['state_meta']['is_stale']);

        Http::assertNothingSent();
    }

    public function test_resolve_for_api_caches_live_payload(): void
    {
        Cache::flush();

        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();
        $service = app(ZoneAutomationStateService::class);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_RECIRC',
                'state_label' => 'Рециркуляция',
                'state_details' => ['failed' => false],
                'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
                'current_levels' => [],
                'active_processes' => [],
                'timeline' => [],
            ], 200),
        ]);

        $payload = $service->resolveForApi($zone);

        $this->assertSame('TANK_RECIRC', $payload['state']);
        $this->assertSame('live', $payload['state_meta']['source']);
        $this->assertFalse($payload['state_meta']['is_stale']);

        $cached = $service->getCachedState($zone->id);
        $this->assertIsArray($cached);
        $this->assertSame('TANK_RECIRC', $cached['state']);

        Http::assertSent(function (HttpRequest $request) use ($zone): bool {
            return $request->url() === "{$this->automationEngineUrl()}/zones/{$zone->id}/state"
                && $request->hasHeader('Authorization', 'Bearer test-scheduler-token')
                && $request->hasHeader('X-Trace-Id');
        });
    }

    public function test_resolve_returns_null_when_upstream_and_cache_unavailable(): void
    {
        Cache::flush();

        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();
        $service = app(ZoneAutomationStateService::class);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response(['message' => 'down'], 503),
        ]);

        $this->assertNull($service->resolve($zone));
    }

    public function test_resolve_keeps_ae4_failure_without_biz_ae3_alert(): void
    {
        Cache::flush();
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();
        $service = app(ZoneAutomationStateService::class);
        $human = 'Команда ae4-t1-z1-s1 завершилась статусом ERROR, ожидался DONE';

        // Без сида biz_ae3_*: сбой AE4 должен доехать через resolveForApi → decorate.
        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IDLE',
                'state_label' => 'Ожидание',
                'state_details' => [
                    'failed' => true,
                    'error_code' => 'ae4_command_not_done',
                    'error_message' => $human,
                    'human_error_message' => $human,
                ],
                'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
                'current_levels' => [],
                'active_processes' => [],
                'timeline' => [],
            ], 200),
        ]);

        $payload = $service->resolveForApi($zone);

        $this->assertTrue((bool) ($payload['state_details']['failed'] ?? false));
        $this->assertSame('ae4_command_not_done', $payload['state_details']['error_code']);
        $this->assertSame($human, $payload['state_details']['human_error_message']);
        $this->assertStringNotContainsString(
            'Внутренняя ошибка системы',
            (string) $payload['state_details']['human_error_message'],
        );
    }

    public function test_decorate_clears_ae3_failure_when_policy_alert_gone(): void
    {
        Cache::flush();
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();
        $service = app(ZoneAutomationStateService::class);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'READY',
                'state_label' => 'Полив — сбой',
                'current_stage' => 'irrigation_check',
                'state_details' => [
                    'failed' => true,
                    'error_code' => 'irr_state_mismatch',
                    'error_message' => 'IRR mismatch',
                    'human_error_message' => 'Состояние IRR-ноды не совпало',
                ],
                'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
                'current_levels' => [],
                'active_processes' => [],
                'timeline' => [],
            ], 200),
        ]);

        $payload = $service->resolveForApi($zone);

        $this->assertFalse((bool) ($payload['state_details']['failed'] ?? false));
        $this->assertNull($payload['state_details']['error_code'] ?? null);
        $this->assertNull($payload['state_details']['human_error_message'] ?? null);
    }

    public function test_ae4_state_payload_includes_unattended_fields(): void
    {
        Cache::flush();
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $zone = Zone::factory()->create(['automation_runtime' => 'ae4']);
        $apiUrl = $this->automationEngineUrl();
        $service = app(ZoneAutomationStateService::class);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IDLE',
                'state_label' => 'Ожидание',
                'state_details' => ['failed' => false],
                'unattended_ready' => false,
                'unattended_blockers' => [
                    [
                        'reason_code' => 'control_mode_manual',
                        'human_message' => 'Ручной режим — уйти нельзя',
                    ],
                ],
                'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
                'current_levels' => [],
                'active_processes' => [],
                'timeline' => [],
            ], 200),
        ]);

        $payload = $service->resolveForApi($zone);

        $this->assertArrayHasKey('unattended_ready', $payload);
        $this->assertFalse((bool) $payload['unattended_ready']);
        $this->assertIsArray($payload['unattended_blockers'] ?? null);
        $this->assertSame(
            'Ручной режим — уйти нельзя',
            $payload['unattended_blockers'][0]['human_message'] ?? null,
        );

        $unattendedBlob = json_encode([
            $payload['unattended_ready'],
            $payload['unattended_blockers'],
        ], JSON_UNESCAPED_UNICODE);
        $this->assertIsString($unattendedBlob);
        foreach (['tank_filling', 'tank_recirc', 'irrigating', 'TANK_FILLING'] as $stageName) {
            $this->assertStringNotContainsString(
                $stageName,
                $unattendedBlob,
                "unattended fields must not carry tank stage name {$stageName}",
            );
        }
    }

    public function test_decorate_keeps_unattended_when_clearing_ae3_terminal_failure(): void
    {
        Cache::flush();
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $zone = Zone::factory()->create(['automation_runtime' => 'ae4']);
        $apiUrl = $this->automationEngineUrl();
        $service = app(ZoneAutomationStateService::class);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'READY',
                'state_label' => 'Полив — сбой',
                'state_details' => [
                    'failed' => true,
                    'error_code' => 'irr_state_mismatch',
                    'error_message' => 'IRR mismatch',
                    'human_error_message' => 'Состояние IRR-ноды не совпало',
                ],
                'unattended_ready' => false,
                'unattended_blockers' => [
                    [
                        'reason_code' => 'telegram_not_verified',
                        'human_message' => 'Telegram не проверен командой alerts:telegram-test',
                    ],
                ],
                'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
                'current_levels' => [],
                'active_processes' => [],
                'timeline' => [],
            ], 200),
        ]);

        $payload = $service->resolveForApi($zone);

        $this->assertFalse((bool) ($payload['state_details']['failed'] ?? false));
        $this->assertArrayHasKey('unattended_ready', $payload);
        $this->assertFalse((bool) $payload['unattended_ready']);
        $this->assertSame(
            'telegram_not_verified',
            $payload['unattended_blockers'][0]['reason_code'] ?? null,
        );
    }

    public function test_decorate_uses_catalog_when_runtime_human_error_message_empty(): void
    {
        $zone = Zone::factory()->create();
        $this->seedActivePolicyManagedAlert($zone);
        $service = app(ZoneAutomationStateService::class);

        $payload = [
            'zone_id' => $zone->id,
            'state' => 'IDLE',
            'state_label' => 'Ожидание',
            'state_details' => [
                'failed' => true,
                'error_code' => 'ae3_task_failed',
                'error_message' => null,
                'human_error_message' => null,
            ],
            'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
            'current_levels' => [],
            'active_processes' => [],
            'timeline' => [],
        ];

        $method = new \ReflectionMethod(ZoneAutomationStateService::class, 'decorateStatePayload');
        $decorated = $method->invoke($service, $payload, false, 'live', $zone);

        $this->assertNotSame('', trim((string) ($decorated['state_details']['human_error_message'] ?? '')));
        $this->assertNotNull($decorated['state_details']['human_error_message']);
    }
}
