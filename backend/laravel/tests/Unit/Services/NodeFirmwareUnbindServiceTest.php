<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Models\Zone;
use App\Services\NodeFirmwareUnbindService;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeFirmwareUnbindServiceTest extends TestCase
{
    use RefreshDatabase;

    private NodeFirmwareUnbindService $service;

    protected function setUp(): void
    {
        parent::setUp();
        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.history_logger.token', 'test-token');
        $this->service = app(NodeFirmwareUnbindService::class);
    }

    public function test_build_unbind_config_forces_temp_namespace(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-unbind-1',
            'type' => 'ph',
            'config' => [
                'node_id' => 'nd-unbind-1',
                'version' => 3,
                'type' => 'ph',
                'gh_uid' => 'gh-1',
                'zone_uid' => 'zn-1',
                'channels' => [['name' => 'ph', 'type' => 'SENSOR']],
                'mqtt' => ['host' => 'mqtt.local', 'port' => 1883],
                'node_secret' => 'secret-32-bytes-padding-xxxxxx',
            ],
        ]);

        $config = $this->service->buildUnbindConfig($node);

        $this->assertSame('gh-temp', $config['gh_uid']);
        $this->assertSame('zn-temp', $config['zone_uid']);
        $this->assertSame('nd-unbind-1', $config['node_id']);
        $this->assertSame('ph', $config['type']);
        $this->assertArrayHasKey('mqtt', $config);
    }

    public function test_publish_temp_namespace_config_posts_to_history_logger(): void
    {
        Http::fake([
            'history-logger:9300/nodes/*/config' => Http::response(['status' => 'ok'], 200),
        ]);

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-unbind-pub',
            'zone_id' => $zone->id,
            'type' => 'ec',
            'config' => [
                'node_id' => 'nd-unbind-pub',
                'version' => 3,
                'type' => 'ec',
                'channels' => [],
                'mqtt' => ['configured' => true],
            ],
        ]);

        $ok = $this->service->publishTempNamespaceConfig($node);

        $this->assertTrue($ok);
        Http::assertSent(function ($request) use ($node, $zone) {
            return $request->url() === "http://history-logger:9300/nodes/{$node->uid}/config"
                && ($request->data()['zone_id'] ?? null) === $zone->id
                && ($request->data()['zone_uid'] ?? null) === $zone->uid
                && ($request->data()['greenhouse_uid'] ?? null) === $zone->greenhouse->uid
                && ($request->data()['config']['gh_uid'] ?? null) === 'gh-temp'
                && ($request->data()['config']['zone_uid'] ?? null) === 'zn-temp';
        });
    }

    public function test_publish_returns_false_when_hl_fails_without_throwing(): void
    {
        Http::fake([
            'history-logger:9300/nodes/*/config' => Http::response(['error' => 'boom'], 500),
        ]);

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $ok = $this->service->publishTempNamespaceConfig($node);

        $this->assertFalse($ok);
    }

    public function test_publish_skips_when_no_zone(): void
    {
        Http::fake();
        $node = DeviceNode::factory()->create(['zone_id' => null]);

        $ok = $this->service->publishTempNamespaceConfig($node);

        $this->assertFalse($ok);
        Http::assertNothingSent();
    }

    public function test_mirror_temp_namespace_in_stored_config(): void
    {
        $node = DeviceNode::factory()->create([
            'config' => ['gh_uid' => 'gh-1', 'zone_uid' => 'zn-1', 'version' => 3],
        ]);

        $this->service->mirrorTempNamespaceInStoredConfig($node);

        $this->assertSame('gh-temp', $node->config['gh_uid']);
        $this->assertSame('zn-temp', $node->config['zone_uid']);
    }
}
