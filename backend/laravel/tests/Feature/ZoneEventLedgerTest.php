<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\Greenhouse;
use App\Models\DeviceNode;
use App\Models\Command;
use App\Models\Alert;
use App\Events\CommandStatusUpdated;
use App\Events\AlertCreated;
use App\Events\ZoneUpdated;
use Tests\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Event;
use Tests\TestCase;

class ZoneEventLedgerTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);
        return $user->createToken('test')->plainTextToken;
    }

    public function test_zone_events_table_has_correct_structure(): void
    {
        $this->assertTrue(
            DB::getSchemaBuilder()->hasTable('zone_events'),
            'Таблица zone_events должна существовать'
        );

        $columns = DB::getSchemaBuilder()->getColumnListing('zone_events');
        
        $this->assertContains('id', $columns);
        $this->assertContains('zone_id', $columns);
        $this->assertContains('type', $columns);
        $this->assertContains('entity_type', $columns);
        $this->assertContains('entity_id', $columns);
        $this->assertContains('payload_json', $columns);
        $this->assertContains('server_ts', $columns);
        $this->assertContains('created_at', $columns);
    }

    public function test_command_status_updated_records_to_zone_events(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        // Создаем команду напрямую через DB (вне транзакции теста)
        $cmdId = 'test-cmd-' . uniqid();
        
        // Завершаем транзакцию теста перед вставкой команды
        DB::commit();
        
        $commandId = DB::table('commands')->insertGetId([
            'zone_id' => $zone->id,
            'cmd' => 'test',
            'cmd_id' => $cmdId,
            'status' => Command::STATUS_QUEUED,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        // Создаем событие
        $event = new CommandStatusUpdated(
            commandId: $cmdId,
            status: Command::STATUS_SENT,
            message: 'Command sent',
            zoneId: $zone->id
        );

        // Вызываем метод broadcasted() напрямую (в реальности вызывается после broadcast)
        $event->broadcasted();
        
        // Начинаем новую транзакцию для проверок
        DB::beginTransaction();

        // Проверяем, что событие записано в zone_events
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'command_status',
            'entity_type' => 'command',
            'entity_id' => $cmdId,
        ]);

        $zoneEvent = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'command_status')
            ->first();

        $this->assertNotNull($zoneEvent);
        $this->assertNotNull($zoneEvent->server_ts);
        $this->assertNotNull($zoneEvent->payload_json);
        
        $payload = json_decode($zoneEvent->payload_json, true);
        $this->assertEquals(Command::STATUS_SENT, $payload['status']);
        $this->assertEquals('Command sent', $payload['message']);
        $this->assertArrayHasKey('ws_event_id', $payload); // event_id из WS события
    }

    public function test_alert_created_records_to_zone_events(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $alertData = [
            'id' => 1,
            'zone_id' => $zone->id,
            'code' => 'test_alert',
            'severity' => 'ERROR',
            'status' => 'ACTIVE',
        ];

        $event = new AlertCreated($alertData);
        $event->broadcasted();

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'alert_created',
            'entity_type' => 'alert',
            'entity_id' => $alertData['id'],
        ]);
    }

    public function test_events_api_returns_events_in_order(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $token = $this->token();

        // Создаем несколько событий с задержкой для проверки порядка
        $now = now();
        $eventIds = [];
        
        for ($i = 1; $i <= 5; $i++) {
            $eventId = DB::table('zone_events')->insertGetId([
                'zone_id' => $zone->id,
                'type' => 'test_event',
                'entity_type' => 'test',
                'entity_id' => $i,
                'payload_json' => json_encode(['order' => $i]),
                'server_ts' => ($now->timestamp + $i) * 1000,
                'created_at' => $now->copy()->addSeconds($i),
            ]);
            $eventIds[] = $eventId;
            usleep(1000); // Небольшая задержка для гарантии порядка
        }

        // Запрашиваем события через API
        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/events");

        $response->assertStatus(200);
        $response->assertJsonStructure([
            'status',
            'data',
            'last_event_id',
            'has_more',
        ]);

        $data = $response->json('data');
        $this->assertCount(5, $data);
        
        // Проверяем порядок по id (строго возрастающий)
        $ids = array_column($data, 'event_id');
        $sortedIds = $ids;
        sort($sortedIds);
        $this->assertEquals($sortedIds, $ids, 'События должны быть отсортированы по event_id по возрастанию');
    }

    public function test_events_api_supports_after_id_pagination(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $token = $this->token();

        // Создаем 10 событий
        $eventIds = [];
        for ($i = 1; $i <= 10; $i++) {
            $eventId = DB::table('zone_events')->insertGetId([
                'zone_id' => $zone->id,
                'type' => 'test_event',
                'entity_type' => 'test',
                'entity_id' => $i,
                'payload_json' => json_encode(['order' => $i]),
                'server_ts' => now()->timestamp * 1000,
                'created_at' => now(),
            ]);
            $eventIds[] = $eventId;
        }

        // Первый запрос - получаем первые 5 событий
        $response1 = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/events?limit=5");

        $response1->assertStatus(200);
        $data1 = $response1->json('data');
        $this->assertCount(5, $data1);
        $lastEventId1 = $response1->json('last_event_id');

        // Второй запрос - получаем события после last_event_id
        $response2 = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/events?after_id={$lastEventId1}&limit=5");

        $response2->assertStatus(200);
        $data2 = $response2->json('data');
        $this->assertCount(5, $data2);

        // Проверяем, что события не пересекаются
        $ids1 = array_column($data1, 'event_id');
        $ids2 = array_column($data2, 'event_id');
        $intersection = array_intersect($ids1, $ids2);
        $this->assertEmpty($intersection, 'События не должны пересекаться между запросами');

        // Проверяем, что все события из второго запроса больше last_event_id
        foreach ($ids2 as $id) {
            $this->assertGreaterThan($lastEventId1, $id, 'Все события должны быть больше after_id');
        }
    }

    public function test_events_api_returns_human_readable_message_field(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $token = $this->token();

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'ALERT_UPDATED',
            'entity_type' => 'alert',
            'entity_id' => '101',
            'payload_json' => json_encode([
                'code' => 'BIZ_HIGH_TEMP',
                'error_count' => 3,
            ]),
            'server_ts' => now()->timestamp * 1000,
            'created_at' => now(),
        ]);

        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone->id}/events");

        $response->assertStatus(200)
            ->assertJsonPath('data.0.type', 'ALERT_UPDATED')
            ->assertJsonPath('data.0.message', 'Алерт BIZ_HIGH_TEMP обновлён (повторений: 3)');
    }

    public function test_cycle_only_filter_does_not_leak_events_from_other_zones(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zoneA = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $zoneB = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $token = $this->token('admin');

        $zoneAEventId = DB::table('zone_events')->insertGetId([
            'zone_id' => $zoneA->id,
            'type' => 'CYCLE_CREATED',
            'entity_type' => 'grow_cycle',
            'entity_id' => '1',
            'payload_json' => json_encode(['cycle_id' => 1]),
            'server_ts' => now()->timestamp * 1000,
            'created_at' => now(),
        ]);

        DB::table('zone_events')->insert([
            'zone_id' => $zoneB->id,
            'type' => 'ALERT_CREATED',
            'entity_type' => 'alert',
            'entity_id' => '2',
            'payload_json' => json_encode([
                'code' => 'BIZ_NO_FLOW',
                'severity' => 'CRITICAL',
            ]),
            'server_ts' => now()->timestamp * 1000,
            'created_at' => now(),
        ]);

        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zoneA->id}/events?cycle_only=1");

        $response->assertStatus(200)
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.event_id', $zoneAEventId)
            ->assertJsonPath('data.0.zone_id', $zoneA->id);
    }

    public function test_events_api_requires_authentication(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $response = $this->getJson("/api/zones/{$zone->id}/events");
        $response->assertStatus(401);
    }

    public function test_events_api_requires_zone_access(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone1 = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $zone2 = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        // Создаем пользователя с доступом только к zone1
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;

        // Пытаемся получить события zone2
        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->getJson("/api/zones/{$zone2->id}/events");

        $canAccess = \App\Helpers\ZoneAccessHelper::canAccessZone($user, $zone2);
        $response->assertStatus($canAccess ? 200 : 403);
    }

    public function test_parallel_events_maintain_strict_order(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        // Симулируем параллельную запись событий
        $eventIds = [];
        $iterations = 10;
        
        // Используем транзакции для симуляции параллельности
        for ($i = 0; $i < $iterations; $i++) {
            DB::beginTransaction();
            try {
                $eventId = DB::table('zone_events')->insertGetId([
                    'zone_id' => $zone->id,
                    'type' => 'parallel_test',
                    'entity_type' => 'test',
                    'entity_id' => $i,
                    'payload_json' => json_encode(['iteration' => $i]),
                    'server_ts' => (now()->timestamp + $i) * 1000,
                    'created_at' => now(),
                ]);
                $eventIds[] = $eventId;
                DB::commit();
            } catch (\Exception $e) {
                DB::rollBack();
                throw $e;
            }
        }

        // Проверяем, что события записаны в строгом порядке
        $events = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'parallel_test')
            ->orderBy('id', 'asc')
            ->get();

        $this->assertCount($iterations, $events);
        
        // Проверяем монотонное возрастание id
        $ids = $events->pluck('id')->toArray();
        for ($i = 1; $i < count($ids); $i++) {
            $this->assertGreaterThan($ids[$i - 1], $ids[$i], "ID должны монотонно возрастать");
        }
    }

    public function test_catch_up_after_websocket_disconnect(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $token = $this->token();

        // Симулируем события, которые были отправлены, пока клиент был отключен
        $baseTime = now()->subMinutes(10);
        $eventIds = [];
        
        for ($i = 1; $i <= 20; $i++) {
            $eventId = DB::table('zone_events')->insertGetId([
                'zone_id' => $zone->id,
                'type' => 'missed_event',
                'entity_type' => 'test',
                'entity_id' => $i,
                'payload_json' => json_encode(['missed' => true, 'index' => $i]),
                'server_ts' => $baseTime->copy()->addSeconds($i)->timestamp * 1000,
                'created_at' => $baseTime->copy()->addSeconds($i),
            ]);
            $eventIds[] = $eventId;
        }

        // Клиент "подключается" и запрашивает все пропущенные события
        $allEvents = [];
        $afterId = null;
        $limit = 10;

        do {
            $url = "/api/zones/{$zone->id}/events" . ($afterId ? "?after_id={$afterId}&limit={$limit}" : "?limit={$limit}");
            $response = $this->withHeader('Authorization', "Bearer {$token}")
                ->getJson($url);

            $response->assertStatus(200);
            $data = $response->json('data');
            $allEvents = array_merge($allEvents, $data);
            $afterId = $response->json('last_event_id');
            $hasMore = $response->json('has_more');
        } while ($hasMore && count($data) > 0);

        // Проверяем, что получены все события
        $this->assertGreaterThanOrEqual(20, count($allEvents), 'Должны быть получены все пропущенные события');

        // Проверяем порядок событий
        $ids = array_column($allEvents, 'event_id');
        $sortedIds = $ids;
        sort($sortedIds);
        $this->assertEquals($sortedIds, $ids, 'События должны быть в строгом порядке');
    }
}
