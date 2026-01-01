<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\Greenhouse;
use App\Models\DeviceNode;
use App\Models\Alert;
use App\Models\Command;
use App\Models\TelemetryLast;
use App\Models\Sensor;
use Tests\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class ZoneSnapshotTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);
        return $user->createToken('test')->plainTextToken;
    }

    public function test_snapshot_includes_last_event_id_and_server_ts(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $token = $this->token();

        // Создаем несколько событий для зоны
        for ($i = 1; $i <= 5; $i++) {
            DB::table('zone_events')->insert([
                'zone_id' => $zone->id,
                'type' => 'test_event',
                'entity_type' => 'test',
                'entity_id' => (string) $i,
                'payload_json' => json_encode(['test' => $i]),
                'server_ts' => (now()->timestamp + $i) * 1000,
                'created_at' => now(),
            ]);
        }

        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/snapshot");

        $response->assertStatus(200);
        $response->assertJsonStructure([
            'status',
            'data' => [
                'snapshot_id',
                'server_ts',
                'last_event_id',
                'zone_id',
                'devices_online_state',
                'active_alerts',
                'latest_telemetry_per_channel',
                'commands_recent',
            ],
        ]);

        $data = $response->json('data');
        $this->assertIsInt($data['last_event_id']);
        $this->assertGreaterThan(0, $data['last_event_id']);
        $this->assertIsInt($data['server_ts']);
        $this->assertNotNull($data['snapshot_id']);
    }

    public function test_snapshot_is_atomic(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $token = $this->token();

        // Создаем начальные события
        $initialEventId = DB::table('zone_events')->insertGetId([
            'zone_id' => $zone->id,
            'type' => 'initial',
            'entity_type' => 'test',
            'entity_id' => '1',
            'payload_json' => json_encode(['test' => 1]),
            'server_ts' => now()->timestamp * 1000,
            'created_at' => now(),
        ]);

        // Получаем snapshot
        $response1 = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/snapshot");

        $response1->assertStatus(200);
        $data1 = $response1->json('data');
        $lastEventId1 = $data1['last_event_id'];
        $serverTs1 = $data1['server_ts'];

        // Создаем новое событие после snapshot
        $newEventId = DB::table('zone_events')->insertGetId([
            'zone_id' => $zone->id,
            'type' => 'new_event',
            'entity_type' => 'test',
            'entity_id' => '2',
            'payload_json' => json_encode(['test' => 2]),
            'server_ts' => now()->timestamp * 1000,
            'created_at' => now(),
        ]);

        // Получаем snapshot еще раз
        $response2 = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/snapshot");

        $response2->assertStatus(200);
        $data2 = $response2->json('data');
        $lastEventId2 = $data2['last_event_id'];

        // Проверяем, что второй snapshot имеет больший last_event_id
        $this->assertGreaterThan($lastEventId1, $lastEventId2);
        $this->assertEquals($newEventId, $lastEventId2);
    }

    public function test_snapshot_includes_devices_online_state(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        
        $token = $this->token();

        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/snapshot");

        $response->assertStatus(200);
        $data = $response->json('data');
        
        $this->assertArrayHasKey('devices_online_state', $data);
        $devices = $data['devices_online_state'];
        
        $this->assertCount(1, $devices);
        
        $device = collect($devices)->firstWhere('id', $node->id);
        
        $this->assertNotNull($device);
        $this->assertEquals('online', $device['status']);
    }

    public function test_snapshot_includes_active_alerts(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $activeAlert1 = Alert::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'ACTIVE',
        ]);
        
        $activeAlert2 = Alert::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'ACTIVE',
        ]);
        
        $resolvedAlert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'RESOLVED',
        ]);
        
        $token = $this->token();

        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/snapshot");

        $response->assertStatus(200);
        $data = $response->json('data');
        
        $this->assertArrayHasKey('active_alerts', $data);
        $alerts = $data['active_alerts'];
        
        // Должны быть только активные алерты
        $this->assertCount(2, $alerts);
        
        $alertIds = array_column($alerts, 'id');
        $this->assertContains($activeAlert1->id, $alertIds);
        $this->assertContains($activeAlert2->id, $alertIds);
        $this->assertNotContains($resolvedAlert->id, $alertIds);
    }

    public function test_snapshot_includes_latest_telemetry_per_channel(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        
        // Создаем телеметрию для разных каналов
        $phSensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'PH',
            'label' => 'ph_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);
        $ecSensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'EC',
            'label' => 'ec_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);
        TelemetryLast::create([
            'sensor_id' => $phSensor->id,
            'last_value' => 6.5,
            'last_ts' => now(),
            'last_quality' => 'GOOD',
        ]);
        
        TelemetryLast::create([
            'sensor_id' => $ecSensor->id,
            'last_value' => 1.8,
            'last_ts' => now(),
            'last_quality' => 'GOOD',
        ]);
        
        $token = $this->token();

        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/snapshot");

        $response->assertStatus(200);
        $data = $response->json('data');
        
        $this->assertArrayHasKey('latest_telemetry_per_channel', $data);
        $telemetry = $data['latest_telemetry_per_channel'];
        
        $this->assertArrayHasKey('ph_sensor', $telemetry);
        $this->assertArrayHasKey('ec_sensor', $telemetry);
        
        $phData = $telemetry['ph_sensor'][$node->id] ?? [];
        $ecData = $telemetry['ec_sensor'][$node->id] ?? [];
        
        $this->assertNotEmpty($phData);
        $this->assertNotEmpty($ecData);
        
        $phValue = collect($phData)->firstWhere('metric_type', 'PH');
        $ecValue = collect($ecData)->firstWhere('metric_type', 'EC');
        
        $this->assertNotNull($phValue);
        $this->assertEquals(6.5, $phValue['value']);
        $this->assertNotNull($ecValue);
        $this->assertEquals(1.8, $ecValue['value']);
    }

    public function test_snapshot_includes_commands_recent(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        
        // Создаем команды с разными статусами
        $cmd1 = Command::create([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'cmd' => 'test_cmd',
            'cmd_id' => 'cmd-1',
            'status' => Command::STATUS_QUEUED,
            'created_at' => now()->subMinutes(5),
        ]);
        
        $cmd2 = Command::create([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'cmd' => 'test_cmd',
            'cmd_id' => 'cmd-2',
            'status' => Command::STATUS_SENT,
            'created_at' => now()->subMinutes(3),
        ]);
        
        $cmd3 = Command::create([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'cmd' => 'test_cmd',
            'cmd_id' => 'cmd-3',
            'status' => Command::STATUS_DONE,
            'created_at' => now()->subMinutes(1),
        ]);
        
        $token = $this->token();

        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/snapshot");

        $response->assertStatus(200);
        $data = $response->json('data');
        
        $this->assertArrayHasKey('commands_recent', $data);
        $commands = $data['commands_recent'];
        
        $this->assertGreaterThanOrEqual(3, count($commands));
        
        $cmdIds = array_column($commands, 'cmd_id');
        $this->assertContains('cmd-1', $cmdIds);
        $this->assertContains('cmd-2', $cmdIds);
        $this->assertContains('cmd-3', $cmdIds);
        
        // Проверяем, что команды отсортированы по created_at desc (самые новые первые)
        $firstCmd = $commands[0];
        $this->assertEquals('cmd-3', $firstCmd['cmd_id']);
    }

    public function test_snapshot_catch_up_after_event_gap(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $token = $this->token();

        // Создаем начальные события
        for ($i = 1; $i <= 10; $i++) {
            DB::table('zone_events')->insert([
                'zone_id' => $zone->id,
                'type' => 'initial_event',
                'entity_type' => 'test',
                'entity_id' => (string) $i,
                'payload_json' => json_encode(['index' => $i]),
                'server_ts' => (now()->timestamp + $i) * 1000,
                'created_at' => now()->subMinutes(10)->addSeconds($i),
            ]);
        }

        // Клиент получает snapshot
        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/snapshot");

        $response->assertStatus(200);
        $data = $response->json('data');
        $lastEventId = $data['last_event_id'];

        // Создаем новые события после snapshot (симулируем пропущенные события)
        for ($i = 11; $i <= 20; $i++) {
            DB::table('zone_events')->insert([
                'zone_id' => $zone->id,
                'type' => 'missed_event',
                'entity_type' => 'test',
                'entity_id' => (string) $i,
                'payload_json' => json_encode(['index' => $i]),
                'server_ts' => (now()->timestamp + $i) * 1000,
                'created_at' => now()->addSeconds($i - 10),
            ]);
        }

        // Клиент запрашивает события после last_event_id для catch-up
        $eventsResponse = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/events?after_id={$lastEventId}");

        $eventsResponse->assertStatus(200);
        $eventsData = $eventsResponse->json('data');
        
        // Должны получить события с ID больше last_event_id из snapshot
        $this->assertGreaterThan(0, count($eventsData));
        
        foreach ($eventsData as $event) {
            $this->assertGreaterThan($lastEventId, $event['event_id']);
        }
        
        // Проверяем порядок событий
        $eventIds = array_column($eventsData, 'event_id');
        $sortedIds = $eventIds;
        sort($sortedIds);
        $this->assertEquals($sortedIds, $eventIds, 'События должны быть в строгом порядке');
    }

    public function test_snapshot_requires_authentication(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $response = $this->getJson("/api/zones/{$zone->id}/snapshot");
        $response->assertStatus(401);
    }
}
