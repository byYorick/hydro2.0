<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\PythonBridgeService;
use Illuminate\Foundation\Testing\RefreshDatabase;
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
        Config::set('services.python_bridge.base_url', 'http://test-bridge');
        Config::set('services.python_bridge.token', 'test-token');

        Http::fake([
            'http://test-bridge/*' => Http::response(['status' => 'ok'], 200),
        ]);
    }

    public function test_send_zone_command_with_explicit_node_uid_and_channel(): void
    {
        $zone = Zone::factory()->create();

        $cmdId = $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => ['duration_sec' => 30],
            'node_uid' => 'nd-pump-1',
            'channel' => 'pump_main',
        ]);

        $this->assertNotEmpty($cmdId);

        Http::assertSent(function ($request) use ($zone) {
            $data = $request->data();
            return $request->url() === "http://test-bridge/bridge/zones/{$zone->id}/commands"
                && $request->hasHeader('Authorization', 'Bearer test-token')
                && isset($data['node_uid']) && $data['node_uid'] === 'nd-pump-1'
                && isset($data['channel']) && $data['channel'] === 'pump_main';
        });
    }

    public function test_send_zone_command_uses_node_from_zone_when_not_specified(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id, 'uid' => 'nd-ph-1']);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'ph_sensor',
            'type' => 'sensor',
            'metric' => 'PH',
        ]);

        $cmdId = $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_PH_CONTROL',
            'params' => [],
        ]);

        $this->assertNotEmpty($cmdId);

        Http::assertSent(function ($request) use ($node) {
            $data = $request->data();

            return isset($data['node_uid']) && $data['node_uid'] === $node->uid
                && isset($data['channel']) && $data['channel'] === 'ph_sensor';
        });
    }

    public function test_send_zone_command_throws_exception_when_no_node_or_channel(): void
    {
        $zone = Zone::factory()->create();
        // Зона без узлов

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessage('node_uid and channel are required');

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
        $this->expectExceptionMessage('node_uid and channel are required');

        $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
        ]);
    }

    public function test_send_zone_command_throws_exception_when_only_node_uid_specified(): void
    {
        $zone = Zone::factory()->create();

        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessage('node_uid and channel are required');

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
        $this->expectExceptionMessage('node_uid and channel are required');

        $this->service->sendZoneCommand($zone, [
            'type' => 'FORCE_IRRIGATION',
            'params' => [],
            // node_uid не указан
            'channel' => 'pump_main',
        ]);
    }
}
