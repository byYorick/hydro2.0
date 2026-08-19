<?php

namespace Tests\Feature;

use Tests\TestCase;

class BoostBrowserLogsTest extends TestCase
{
    public function test_boost_browser_logs_accepts_payload_without_auth_in_testing(): void
    {
        $payload = [
            'logs' => [
                [
                    'type' => 'log',
                    'timestamp' => now()->toIso8601String(),
                    'data' => ['test message', ['meta' => 'value']],
                    'url' => 'http://localhost:8080/logs',
                    'userAgent' => 'PHPUnit',
                ],
            ],
        ];

        $response = $this->postJson('/_boost/browser-logs', $payload);

        $response->assertOk()->assertJson([
            'status' => 'ok',
            'count' => 1,
        ]);
    }

    public function test_boost_browser_logs_uses_configured_browser_channel(): void
    {
        $this->assertNotNull(config('logging.channels.browser'));

        $response = $this->postJson('/_boost/browser-logs', [
            'logs' => [
                [
                    'type' => 'error',
                    'timestamp' => now()->toIso8601String(),
                    'data' => ['browser channel ok'],
                    'url' => 'http://localhost:8080/zones/83',
                    'userAgent' => 'PHPUnit',
                ],
            ],
        ]);

        $response->assertOk()->assertJson(['status' => 'ok', 'count' => 1]);
    }
}
