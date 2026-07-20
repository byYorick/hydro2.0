<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Services\NodeSecretService;
use Illuminate\Support\Facades\Log;
use Tests\TestCase;

class NodeSecretServiceTest extends TestCase
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

    public function test_generate_returns_64_char_hex(): void
    {
        /** @var NodeSecretService $service */
        $service = $this->app->make(NodeSecretService::class);

        $secret = $service->generate();

        $this->assertSame(64, strlen($secret));
        $this->assertMatchesRegularExpression('/^[a-f0-9]{64}$/', $secret);
    }

    public function test_ensure_on_node_generates_and_mutates_config_without_logging_secret(): void
    {
        Log::spy();

        $node = new DeviceNode([
            'id' => 10,
            'uid' => 'nd-secret-ensure',
            'config' => [],
        ]);

        /** @var NodeSecretService $service */
        $service = $this->app->make(NodeSecretService::class);
        $secret = $service->ensureOnNode($node);

        $this->assertSame(64, strlen($secret));
        $this->assertSame($secret, $node->config['node_secret'] ?? null);

        Log::shouldHaveReceived('info')
            ->withArgs(function (string $message, array $context) use ($secret): bool {
                if ($message !== 'Generated per-node node_secret') {
                    return false;
                }

                $encoded = json_encode($context);

                return is_string($encoded)
                    && ! str_contains($encoded, $secret)
                    && ! array_key_exists('node_secret', $context)
                    && ! array_key_exists('secret', $context)
                    && ($context['node_uid'] ?? null) === 'nd-secret-ensure';
            })
            ->once();
    }

    public function test_ensure_on_node_preserves_existing_secret(): void
    {
        $existing = str_repeat('cd', 32);
        $node = new DeviceNode([
            'id' => 11,
            'uid' => 'nd-secret-keep',
            'config' => ['node_secret' => $existing],
        ]);

        /** @var NodeSecretService $service */
        $service = $this->app->make(NodeSecretService::class);

        $this->assertSame($existing, $service->ensureOnNode($node));
        $this->assertSame($existing, $node->config['node_secret']);
    }

    public function test_resolve_returns_per_node_secret(): void
    {
        $secret = bin2hex(random_bytes(32));
        $node = new DeviceNode([
            'id' => 12,
            'uid' => 'nd-secret-resolve',
            'config' => ['node_secret' => $secret],
        ]);

        /** @var NodeSecretService $service */
        $service = $this->app->make(NodeSecretService::class);

        $this->assertSame($secret, $service->resolve($node));
    }

    public function test_resolve_fails_closed_in_production_without_secret(): void
    {
        $this->app['env'] = 'production';
        config(['app.node_default_secret' => 'should-not-use', 'app.key' => 'base64:prod-key']);

        $node = new DeviceNode([
            'id' => 13,
            'uid' => 'nd-secret-prod',
            'config' => [],
        ]);

        /** @var NodeSecretService $service */
        $service = $this->app->make(NodeSecretService::class);

        $this->assertNull($service->resolve($node));
    }

    public function test_resolve_falls_back_outside_production(): void
    {
        $this->app['env'] = 'local';
        config([
            'app.node_default_secret' => 'hydro-default-secret-key-2025',
            'app.key' => 'base64:local-key',
        ]);

        $node = new DeviceNode([
            'id' => 14,
            'uid' => 'nd-secret-dev',
            'config' => [],
        ]);

        /** @var NodeSecretService $service */
        $service = $this->app->make(NodeSecretService::class);

        $this->assertSame('hydro-default-secret-key-2025', $service->resolve($node));
    }
}
