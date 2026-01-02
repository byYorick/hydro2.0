<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class UnassignedNodeErrorsTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_unassigned_errors_table_exists(): void
    {
        // Проверяем, что таблица существует и имеет правильную структуру
        $this->assertTrue(
            DB::getSchemaBuilder()->hasTable('unassigned_node_errors'),
            'Таблица unassigned_node_errors должна существовать'
        );

        $columns = DB::getSchemaBuilder()->getColumnListing('unassigned_node_errors');

        $this->assertContains('hardware_id', $columns);
        $this->assertContains('error_message', $columns);
        $this->assertContains('error_code', $columns);
        $this->assertContains('severity', $columns); // переименовано из error_level
        $this->assertContains('last_payload', $columns); // переименовано из error_data
        $this->assertContains('count', $columns);
        $this->assertContains('first_seen_at', $columns);
        $this->assertContains('last_seen_at', $columns);
        $this->assertContains('node_id', $columns);
    }

    public function test_can_insert_unassigned_error(): void
    {
        $now = now();

        DB::table('unassigned_node_errors')->insert([
            'hardware_id' => 'esp32-test-123',
            'error_message' => 'Test error message',
            'error_code' => 'ERR_TEST',
            'severity' => 'ERROR',
            'topic' => 'hydro/gh-temp/zn-temp/esp32-test-123/error',
            'last_payload' => json_encode(['test' => 'data']),
            'count' => 1,
            'first_seen_at' => $now,
            'last_seen_at' => $now,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        $this->assertDatabaseHas('unassigned_node_errors', [
            'hardware_id' => 'esp32-test-123',
            'error_code' => 'ERR_TEST',
            'severity' => 'ERROR',
        ]);
    }

    public function test_unique_constraint_on_hardware_id_and_code(): void
    {
        $now = now();

        // Вставляем первую запись
        DB::table('unassigned_node_errors')->insert([
            'hardware_id' => 'esp32-test-456',
            'error_message' => 'First error',
            'error_code' => 'ERR_FIRST',
            'severity' => 'ERROR',
            'topic' => 'hydro/gh-temp/zn-temp/esp32-test-456/error',
            'count' => 1,
            'first_seen_at' => $now,
            'last_seen_at' => $now,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        // Проверяем, что запись создана
        $this->assertDatabaseHas('unassigned_node_errors', [
            'hardware_id' => 'esp32-test-456',
            'error_code' => 'ERR_FIRST',
        ]);

        $driver = DB::connection()->getDriverName();
        if ($driver !== 'pgsql') {
            $this->markTestSkipped('Unique index check requires PostgreSQL metadata.');
        }

        $index = DB::selectOne("
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'unassigned_node_errors'
              AND indexname = 'unassigned_errors_hardware_code_unique'
        ");

        $this->assertNotNull($index, 'Expected unique index on hardware_id + error_code.');
    }

    public function test_get_zone_unassigned_errors_requires_auth(): void
    {
        $zone = Zone::factory()->create();

        $this->getJson("/api/zones/{$zone->id}/unassigned-errors")
            ->assertStatus(401);
    }

    public function test_get_zone_unassigned_errors(): void
    {
        $token = $this->token();
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'hardware_id' => 'esp32-zone-test',
        ]);

        $now = now();

        // Создаем ошибки для ноды зоны
        DB::table('unassigned_node_errors')->insert([
            [
                'hardware_id' => 'esp32-zone-test',
                'error_message' => 'Error 1',
                'error_code' => 'ERR_1',
                'severity' => 'ERROR',
                'topic' => 'hydro/gh-temp/zn-temp/esp32-zone-test/error',
                'node_id' => $node->id,
                'count' => 1,
                'first_seen_at' => $now,
                'last_seen_at' => $now,
                'created_at' => $now,
                'updated_at' => $now,
            ],
            [
                'hardware_id' => 'esp32-zone-test',
                'error_message' => 'Error 2',
                'error_code' => 'ERR_2',
                'severity' => 'WARNING',
                'topic' => 'hydro/gh-temp/zn-temp/esp32-zone-test/error',
                'node_id' => $node->id,
                'count' => 2,
                'first_seen_at' => $now,
                'last_seen_at' => $now,
                'created_at' => $now,
                'updated_at' => $now,
            ],
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/unassigned-errors");

        $resp->assertOk()
            ->assertJsonStructure([
                'status',
                'data' => [
                    '*' => [
                        'id',
                        'hardware_id',
                        'error_message',
                        'error_code',
                        'severity',
                        'count',
                        'node_id',
                    ],
                ],
                'meta' => [
                    'current_page',
                    'last_page',
                    'per_page',
                    'total',
                ],
            ]);

        $data = $resp->json('data');
        $this->assertCount(2, $data);
        $this->assertEquals('esp32-zone-test', $data[0]['hardware_id']);
    }

    public function test_unassigned_errors_attached_to_node_on_registration(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $now = now();
        $hardwareId = 'esp32-new-node';

        // Создаем ошибку для незарегистрированного узла
        DB::table('unassigned_node_errors')->insert([
            'hardware_id' => $hardwareId,
            'error_message' => 'Node not found error',
            'error_code' => 'ERR_NODE_NOT_FOUND',
            'severity' => 'ERROR',
            'topic' => 'hydro/gh-temp/zn-temp/'.$hardwareId.'/error',
            'node_id' => null, // еще не привязана
            'count' => 3,
            'first_seen_at' => $now->copy()->subHours(2),
            'last_seen_at' => $now,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        // Создаем ноду напрямую (обходим проблему с isolation level в тестах)
        // В реальном коде используется NodeRegistryService::registerNodeFromHello
        $node = DeviceNode::create([
            'uid' => 'nd-clim-'.substr($hardwareId, -8).'-1',
            'hardware_id' => $hardwareId,
            'type' => 'climate',
            'fw_version' => '1.0.0',
            'lifecycle_state' => \App\Enums\NodeLifecycleState::REGISTERED_BACKEND,
            'validated' => true,
            'first_seen_at' => now(),
        ]);

        // Привязываем ноду к зоне
        $node->zone_id = $zone->id;
        $node->save();

        // Вызываем attachUnassignedErrors вручную (обычно вызывается при регистрации)
        $nodeRegistryService = app(\App\Services\NodeRegistryService::class);
        $reflection = new \ReflectionClass($nodeRegistryService);
        $method = $reflection->getMethod('attachUnassignedErrors');
        $method->setAccessible(true);
        $method->invoke($nodeRegistryService, $node);

        // Проверяем, что ошибка была удалена из unassigned_node_errors (после архивирования)
        $this->assertDatabaseMissing('unassigned_node_errors', [
            'hardware_id' => $hardwareId,
            'node_id' => null, // Не должно быть записей с null node_id
        ]);

        // Проверяем, что ошибка была архивирована
        $this->assertDatabaseHas('unassigned_node_errors_archive', [
            'hardware_id' => $hardwareId,
            'node_id' => $node->id,
            'error_code' => 'ERR_NODE_NOT_FOUND',
        ]);

        // Проверяем, что alert создан
        $this->assertDatabaseHas('alerts', [
            'zone_id' => $zone->id,
            'code' => 'infra_node_error_ERR_NODE_NOT_FOUND',
            'source' => 'infra',
            'status' => 'ACTIVE',
        ]);

        // Проверяем, что в alert сохранены count, first_seen_at, last_seen_at
        $alert = \App\Models\Alert::where('zone_id', $zone->id)
            ->where('code', 'infra_node_error_ERR_NODE_NOT_FOUND')
            ->first();

        $this->assertNotNull($alert);
        $this->assertEquals(3, $alert->details['count'] ?? 0, 'Count должен быть сохранен из unassigned error');
        $this->assertArrayHasKey('first_seen_at', $alert->details ?? []);
        $this->assertArrayHasKey('last_seen_at', $alert->details ?? []);

        // Проверяем, что создан zone_event для прозрачности
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'unassigned_attached',
        ]);
    }

    public function test_unassigned_errors_filtered_by_severity(): void
    {
        $token = $this->token();
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'hardware_id' => 'esp32-filter-test',
        ]);

        $now = now();

        DB::table('unassigned_node_errors')->insert([
            [
                'hardware_id' => 'esp32-filter-test',
                'error_message' => 'Critical error',
                'error_code' => 'ERR_CRITICAL',
                'severity' => 'CRITICAL',
                'topic' => 'hydro/gh-temp/zn-temp/esp32-filter-test/error',
                'node_id' => $node->id,
                'count' => 1,
                'first_seen_at' => $now,
                'last_seen_at' => $now,
                'created_at' => $now,
                'updated_at' => $now,
            ],
            [
                'hardware_id' => 'esp32-filter-test',
                'error_message' => 'Warning',
                'error_code' => 'ERR_WARNING',
                'severity' => 'WARNING',
                'topic' => 'hydro/gh-temp/zn-temp/esp32-filter-test/error',
                'node_id' => $node->id,
                'count' => 1,
                'first_seen_at' => $now,
                'last_seen_at' => $now,
                'created_at' => $now,
                'updated_at' => $now,
            ],
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/unassigned-errors?severity=CRITICAL");

        $resp->assertOk();
        $data = $resp->json('data');
        $this->assertCount(1, $data);
        $this->assertEquals('CRITICAL', $data[0]['severity']);
    }

    public function test_unassigned_errors_with_null_error_code(): void
    {
        $now = now();

        // Проверяем, что можем вставлять ошибки с NULL error_code
        DB::table('unassigned_node_errors')->insert([
            'hardware_id' => 'esp32-null-code',
            'error_message' => 'Error without code',
            'error_code' => null,
            'severity' => 'ERROR',
            'topic' => 'hydro/gh-temp/zn-temp/esp32-null-code/error',
            'count' => 1,
            'first_seen_at' => $now,
            'last_seen_at' => $now,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        $this->assertDatabaseHas('unassigned_node_errors', [
            'hardware_id' => 'esp32-null-code',
            'error_code' => null,
        ]);
    }
}
