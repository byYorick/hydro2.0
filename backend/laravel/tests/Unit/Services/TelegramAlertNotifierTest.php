<?php

namespace Tests\Unit\Services;

use App\Models\Alert;
use App\Models\Zone;
use App\Services\AlertService;
use App\Services\TelegramAlertNotifier;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class TelegramAlertNotifierTest extends TestCase
{
    use RefreshDatabase;

    private const BOT_TOKEN = '123456:test-bot-token';

    private const CHAT_ID = '-1001234567890';

    protected function setUp(): void
    {
        parent::setUp();

        config([
            'services.telegram.bot_token' => self::BOT_TOKEN,
            'services.telegram.chat_ids' => [self::CHAT_ID],
            'alerts.telegram.enabled' => true,
            'alerts.telegram.dedup_ttl_seconds' => 60,
        ]);

        Cache::flush();
    }

    public function test_critical_alert_create_triggers_telegram_notification(): void
    {
        Http::fake([
            'api.telegram.org/*' => Http::response(['ok' => true], 200),
        ]);

        $zone = Zone::factory()->create();
        $service = app(AlertService::class);

        $service->create([
            'zone_id' => $zone->id,
            'code' => 'biz_correction_exhausted',
            'type' => 'correction_exhausted',
            'source' => 'biz',
            'severity' => 'critical',
            'details' => ['message' => 'Коррекция исчерпана'],
        ]);

        Http::assertSent(function ($request) {
            return str_contains($request->url(), '/bot'.self::BOT_TOKEN.'/sendMessage')
                && $request['chat_id'] === self::CHAT_ID
                && str_contains((string) $request['text'], 'CRITICAL');
        });
    }

    public function test_warning_alert_does_not_trigger_telegram_notification(): void
    {
        Http::fake();

        $zone = Zone::factory()->create();
        $service = app(AlertService::class);

        $service->create([
            'zone_id' => $zone->id,
            'code' => 'biz_ph_drift',
            'type' => 'ph_drift',
            'source' => 'biz',
            'severity' => 'warning',
            'details' => ['message' => 'Небольшой дрейф pH'],
        ]);

        Http::assertNothingSent();
    }

    public function test_telegram_dedup_suppresses_duplicate_for_same_code_and_zone(): void
    {
        Http::fake([
            'api.telegram.org/*' => Http::response(['ok' => true], 200),
        ]);

        $zone = Zone::factory()->create();
        $notifier = app(TelegramAlertNotifier::class);

        $alertPayload = [
            'zone_id' => $zone->id,
            'code' => 'biz_irrigation_estop',
            'type' => 'irrigation_estop',
            'source' => 'biz',
            'severity' => 'critical',
            'status' => 'ACTIVE',
            'details' => ['message' => 'E-STOP'],
            'created_at' => now(),
        ];

        $first = Alert::factory()->create($alertPayload);
        $second = Alert::factory()->create(array_merge($alertPayload, [
            'details' => ['message' => 'E-STOP повтор'],
        ]));

        $notifier->notifyIfEligible($first);
        $notifier->notifyIfEligible($second);

        Http::assertSentCount(1);
    }

    public function test_error_severity_triggers_telegram_notification(): void
    {
        Http::fake([
            'api.telegram.org/*' => Http::response(['ok' => true], 200),
        ]);

        $notifier = app(TelegramAlertNotifier::class);
        $alert = Alert::factory()->create([
            'zone_id' => null,
            'code' => 'mqtt_broker_down',
            'source' => 'infra',
            'severity' => 'error',
            'status' => 'ACTIVE',
        ]);

        $notifier->notifyIfEligible($alert);

        Http::assertSentCount(1);
    }

    public function test_skips_notification_when_telegram_not_configured(): void
    {
        Http::fake();
        config([
            'services.telegram.bot_token' => null,
            'services.telegram.chat_ids' => [],
        ]);

        $notifier = app(TelegramAlertNotifier::class);
        $alert = Alert::factory()->create([
            'severity' => 'critical',
            'status' => 'ACTIVE',
        ]);

        $notifier->notifyIfEligible($alert);

        Http::assertNothingSent();
    }
}
