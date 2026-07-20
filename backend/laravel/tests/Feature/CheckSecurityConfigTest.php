<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class CheckSecurityConfigTest extends TestCase
{
    private string $originalEnv;

    protected function setUp(): void
    {
        parent::setUp();
        $this->originalEnv = (string) $this->app['env'];
    }

    protected function tearDown(): void
    {
        $this->app['env'] = $this->originalEnv;
        parent::tearDown();
    }

    public function test_check_security_config_skips_outside_production_and_notes_provisioning_token(): void
    {
        $this->app['env'] = 'testing';

        $exitCode = Artisan::call('security:check-config');
        $output = Artisan::output();

        $this->assertSame(0, $exitCode);
        $this->assertStringContainsString('provisioning_token is deprecated', $output);
        $this->assertStringContainsString('Not in production', $output);
    }

    public function test_check_security_config_fails_on_hardcoded_node_default_secret_in_production(): void
    {
        $this->app['env'] = 'production';

        config([
            'services.python_bridge.token' => 'py-token',
            'services.python_bridge.ingest_token' => 'ingest-token',
            'services.history_logger.token' => 'hl-token',
            'database.connections.pgsql.password' => 'db-pass',
            'services.mqtt.password' => 'mqtt-pass',
            'app.key' => 'base64:'.base64_encode(str_repeat('k', 32)),
            'app.node_default_secret' => 'hydro-default-secret-key-2025',
        ]);

        $exitCode = Artisan::call('security:check-config');
        $output = Artisan::output();

        $this->assertSame(1, $exitCode);
        $this->assertStringContainsString('NODE_DEFAULT_SECRET is the insecure hardcoded default', $output);
    }

    public function test_check_security_config_ok_in_production_without_shared_node_secret(): void
    {
        $this->app['env'] = 'production';

        config([
            'services.python_bridge.token' => 'py-token',
            'services.python_bridge.ingest_token' => 'ingest-token',
            'services.history_logger.token' => 'hl-token',
            'database.connections.pgsql.password' => 'db-pass',
            'services.mqtt.password' => 'mqtt-pass',
            'app.key' => 'base64:'.base64_encode(str_repeat('k', 32)),
            'app.node_default_secret' => null,
        ]);

        $exitCode = Artisan::call('security:check-config');
        $output = Artisan::output();

        $this->assertSame(0, $exitCode);
        $this->assertStringContainsString('Security configuration OK', $output);
    }
}
