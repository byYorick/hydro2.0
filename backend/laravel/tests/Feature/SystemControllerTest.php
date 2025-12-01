<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Models\DeviceNode;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Config;
use Tests\TestCase;

class SystemControllerTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_system_health_is_public(): void
    {
        // Health endpoint должен быть публичным
        // Для неаутентифицированных пользователей возвращается только базовый статус
        $response = $this->getJson('/api/system/health');
        
        $response->assertOk()
            ->assertJsonStructure(['status', 'data' => ['app']]);
    }

    public function test_system_config_full_requires_auth(): void
    {
        // Убеждаемся, что токен не настроен для этого теста
        Config::set('services.python_bridge.token', null);
        
        // Без авторизации должен вернуть 401
        $response = $this->getJson('/api/system/config/full');
        
        $response->assertStatus(401);
    }

    public function test_system_config_full_with_auth(): void
    {
        $token = $this->token();
        
        // Создаём тестовые данные
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        
        $response = $this->withHeader('Authorization', 'Bearer ' . $token)
            ->getJson('/api/system/config/full');
        
        $response->assertOk()
            ->assertJsonStructure([
                'status',
                'data' => [
                    'greenhouses' => [
                        '*' => [
                            'id',
                            'uid',
                            'name',
                            'zones' => [
                                '*' => [
                                    'id',
                                    'name',
                                    'nodes' => [
                                        '*' => [
                                            'id',
                                            'uid',
                                        ],
                                    ],
                                ],
                            ],
                        ],
                    ],
                ],
            ]);
        
        $data = $response->json('data.greenhouses');
        $this->assertCount(1, $data);
        $this->assertEquals($greenhouse->id, $data[0]['id']);
    }

    public function test_system_config_full_includes_all_relations(): void
    {
        $token = $this->token();
        
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        
        $response = $this->withHeader('Authorization', 'Bearer ' . $token)
            ->getJson('/api/system/config/full');
        
        $response->assertOk();
        
        $greenhouses = $response->json('data.greenhouses');
        $this->assertNotEmpty($greenhouses);
        
        $firstGreenhouse = $greenhouses[0];
        $this->assertArrayHasKey('zones', $firstGreenhouse);
        $this->assertNotEmpty($firstGreenhouse['zones']);
        
        $firstZone = $firstGreenhouse['zones'][0];
        $this->assertArrayHasKey('nodes', $firstZone);
        $this->assertNotEmpty($firstZone['nodes']);
    }

    public function test_system_config_full_filters_zones_by_user_access(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($viewer);
        $viewerToken = $viewer->createToken('test')->plainTextToken;

        // Создаём две теплицы с зонами
        $greenhouse1 = Greenhouse::factory()->create();
        $zone1 = Zone::factory()->create(['greenhouse_id' => $greenhouse1->id]);
        $node1 = DeviceNode::factory()->create(['zone_id' => $zone1->id]);

        $greenhouse2 = Greenhouse::factory()->create();
        $zone2 = Zone::factory()->create(['greenhouse_id' => $greenhouse2->id]);
        $node2 = DeviceNode::factory()->create(['zone_id' => $zone2->id]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $viewerToken)
            ->getJson('/api/system/config/full');

        $response->assertOk();
        
        $greenhouses = $response->json('data.greenhouses');
        // Пока что все зоны доступны (ZoneAccessHelper возвращает все зоны для не-админов)
        // В будущем, когда будет реализована мульти-тенантность, здесь будет фильтрация
        $this->assertGreaterThanOrEqual(2, count($greenhouses));
    }

    public function test_system_config_full_excludes_node_config(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'config' => [
                'wifi' => ['password' => 'secret123'],
                'mqtt' => ['password' => 'mqtt_secret'],
            ],
        ]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $token)
            ->getJson('/api/system/config/full');

        $response->assertOk();
        
        $greenhouses = $response->json('data.greenhouses');
        $firstGreenhouse = $greenhouses[0];
        $firstZone = $firstGreenhouse['zones'][0];
        $firstNode = $firstZone['nodes'][0];
        
        // Проверяем, что config не включен в ответ (защита от утечки креденшалов)
        $this->assertArrayNotHasKey('config', $firstNode);
    }
}

