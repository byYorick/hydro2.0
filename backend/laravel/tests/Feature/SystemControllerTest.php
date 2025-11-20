<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Models\DeviceNode;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SystemControllerTest extends TestCase
{
    use RefreshDatabase;

    private function token(): string
    {
        $user = User::factory()->create();
        return $user->createToken('test')->plainTextToken;
    }

    public function test_system_health_is_public(): void
    {
        // Health endpoint должен быть публичным
        $response = $this->getJson('/api/system/health');
        
        $response->assertOk()
            ->assertJsonStructure(['status', 'data' => ['app', 'db']]);
    }

    public function test_system_config_full_requires_auth(): void
    {
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
}

