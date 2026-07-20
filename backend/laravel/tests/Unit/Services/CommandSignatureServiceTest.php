<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Services\CommandSignatureService;
use App\Services\NodeSecretService;
use Tests\TestCase;

class CommandSignatureServiceTest extends TestCase
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

    public function test_sign_command_uses_per_node_secret(): void
    {
        $secret = bin2hex(random_bytes(32));
        $node = new DeviceNode([
            'id' => 1,
            'uid' => 'nd-cmd-1',
            'config' => ['node_secret' => $secret],
        ]);

        /** @var CommandSignatureService $service */
        $service = $this->app->make(CommandSignatureService::class);
        $signed = $service->signCommand($node, ['cmd' => 'restart']);

        $this->assertArrayHasKey('ts', $signed);
        $this->assertArrayHasKey('sig', $signed);
        $this->assertTrue($service->verifySignature($node, $signed));
    }

    public function test_sign_command_fails_closed_in_production_without_node_secret(): void
    {
        $this->app['env'] = 'production';
        config(['app.node_default_secret' => null, 'app.key' => 'base64:prod-app-key']);

        $node = new DeviceNode([
            'id' => 2,
            'uid' => 'nd-cmd-prod',
            'config' => [],
        ]);

        /** @var CommandSignatureService $service */
        $service = $this->app->make(CommandSignatureService::class);

        $this->expectException(\RuntimeException::class);
        $this->expectExceptionMessage('Node secret not configured');

        $service->signCommand($node, ['cmd' => 'restart']);
    }

    public function test_resolve_falls_back_outside_production(): void
    {
        $this->app['env'] = 'testing';
        config([
            'app.node_default_secret' => 'hydro-default-secret-key-2025',
            'app.key' => 'base64:test-key',
        ]);

        $node = new DeviceNode([
            'id' => 3,
            'uid' => 'nd-cmd-dev',
            'config' => [],
        ]);

        /** @var NodeSecretService $secrets */
        $secrets = $this->app->make(NodeSecretService::class);

        $this->assertSame('hydro-default-secret-key-2025', $secrets->resolve($node));
    }

    public function test_resolve_returns_null_in_production_without_per_node_secret(): void
    {
        $this->app['env'] = 'production';
        config(['app.node_default_secret' => null, 'app.key' => 'base64:prod-app-key']);

        $node = new DeviceNode([
            'id' => 4,
            'uid' => 'nd-cmd-prod-null',
            'config' => [],
        ]);

        /** @var NodeSecretService $secrets */
        $secrets = $this->app->make(NodeSecretService::class);

        $this->assertNull($secrets->resolve($node));
    }
}
