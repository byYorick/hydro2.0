<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\PythonBridgeService;
use Tests\RefreshDatabase;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class PythonBridgeServiceTest extends TestCase
{
    use RefreshDatabase;

    private PythonBridgeService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new PythonBridgeService;

        // Настраиваем моки для HTTP и конфига
        // PythonBridgeService теперь использует history-logger для команд зон
        Config::set('services.history_logger.url', 'http://test-bridge');
        Config::set('services.history_logger.token', 'test-token');
        Config::set('services.python_bridge.base_url', 'http://test-bridge');
        Config::set('services.python_bridge.token', 'test-token');

        Http::fake([
            'http://test-bridge/*' => Http::response(['status' => 'ok'], 200),
        ]);
    }

    public function test_send_zone_command_with_explicit_node_uid_and_channel(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id, 'uid' => 'nd-pump-1']);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_main',
            'type' => 'pump',
            'metric' => null,
        ]);

        $cmdId = $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => ['duration_sec' => 30],
            'node_uid' => 'nd-pump-1',
            'channel' => 'pump_main',
        ]);

        $this->assertNotEmpty($cmdId);

        Http::assertSent(function ($request) use ($zone) {
            $data = $request->data();
            $url = $request->url();
            // PythonBridgeService использует history-logger для команд зон
            return str_contains($url, "zones/{$zone->id}/commands")
                && $request->hasHeader('Authorization', 'Bearer test-token')
                && isset($data['node_uid']) && $data['node_uid'] === 'nd-pump-1'
                && isset($data['channel']) && $data['channel'] === 'pump_main';
        });
    }

    public function test_send_zone_command_validates_node_exists_and_belongs_to_zone(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id, 'uid' => 'nd-ph-1']);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'ph_sensor',
            'type' => 'sensor',
            'metric' => 'PH',
        ]);

        // Тест: успешная отправка команды с валидными node_uid и channel
        $cmdId = $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_PH_CONTROL',
            'params' => [],
            'node_uid' => $node->uid,
            'channel' => 'ph_sensor',
        ]);

        $this->assertNotEmpty($cmdId);

        Http::assertSent(function ($request) use ($node) {
            $data = $request->data();

            return isset($data['node_uid']) && $data['node_uid'] === $node->uid
                && isset($data['channel']) && $data['channel'] === 'ph_sensor';
        });
    }

    public function test_send_zone_command_throws_exception_when_node_not_found(): void
    {
        $zone = Zone::factory()->create();

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/Node non-existent-node not found or not assigned to zone \d+/');

        $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
            'node_uid' => 'non-existent-node',
            'channel' => 'pump_main',
        ]);
    }

    public function test_send_zone_command_throws_exception_when_node_not_in_zone(): void
    {
        $zone1 = Zone::factory()->create();
        $zone2 = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone1->id, 'uid' => 'nd-ph-1']);

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/Node nd-ph-1 not found or not assigned to zone \d+/');

        $this->service->sendZoneCommand($zone2, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
            'node_uid' => $node->uid,
            'channel' => 'pump_main',
        ]);
    }

    public function test_send_zone_command_throws_exception_when_channel_not_found(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id, 'uid' => 'nd-ph-1']);

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/Channel non-existent-channel not found on node nd-ph-1/');

        $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
            'node_uid' => $node->uid,
            'channel' => 'non-existent-channel',
        ]);
    }

    public function test_send_zone_command_throws_exception_when_no_node_or_channel(): void
    {
        $zone = Zone::factory()->create();
        // Зона без узлов

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/Unable to auto-resolve node_uid and channel/');

        $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
        ]);
    }

    public function test_send_zone_command_throws_exception_when_node_has_no_channels(): void
    {
        $zone = Zone::factory()->create();
        DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'uid' => 'nd-ph-1',
        ]);
        // Узел без каналов

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/Unable to auto-resolve node_uid and channel/');

        $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
        ]);
    }

    public function test_send_zone_command_throws_exception_when_only_node_uid_specified(): void
    {
        $zone = Zone::factory()->create();

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/Unable to auto-resolve node_uid and channel/');

        $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
            'node_uid' => 'nd-pump-1',
            // channel не указан
        ]);
    }

    public function test_send_zone_command_throws_exception_when_only_channel_specified(): void
    {
        $zone = Zone::factory()->create();

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/Unable to auto-resolve node_uid and channel/');

        $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
            // node_uid не указан
            'channel' => 'pump_main',
        ]);
    }
}
