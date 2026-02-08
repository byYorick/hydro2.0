<?php

namespace Database\Seeders;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\GrowStageTemplate;
use App\Models\GrowCycle;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Carbon\Carbon;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

/**
 * Seeder для E2E тестов Automation Engine.
 * Создает зону с полным набором capabilities, bindings и активным grow-cycle.
 *
 * Зона соответствует UID из node-sim-config.yaml:
 * - gh_uid: gh-test-1
 * - zone_uid: zn-test-1
 * - node_uid: nd-ph-esp32una
 */
class AutomationEngineE2ESeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание данных для E2E тестов Automation Engine ===');

        // 1. Создаем теплицу
        $greenhouse = Greenhouse::firstOrCreate(
            ['uid' => 'gh-test-1'],
            [
                'name' => 'E2E Test Greenhouse',
                'timezone' => 'UTC',
                'type' => 'indoor',
                'coordinates' => ['lat' => 0.0, 'lon' => 0.0],
                'description' => 'Greenhouse for E2E automation engine tests',
                'provisioning_token' => Str::random(32),
            ]
        );
        if (! $greenhouse->provisioning_token) {
            $greenhouse->provisioning_token = Str::random(32);
            $greenhouse->save();
        }

        // 2. Создаем зону с полным набором capabilities
        $zone = Zone::firstOrCreate(
            [
                'greenhouse_id' => $greenhouse->id,
                'uid' => 'zn-test-1',
            ],
            [
                'name' => 'E2E Automation Zone',
                'description' => 'Zone for E2E automation engine tests',
                'status' => 'RUNNING',
                'capabilities' => [
                    'ph_control' => true,
                    'ec_control' => true,
                    'climate_control' => true,
                    'light_control' => true,
                    'irrigation_control' => true,
                    'recirculation' => true,
                    'flow_sensor' => true,
                ],
                'hardware_profile' => [
                    'has_ph_sensor' => true,
                    'has_ec_sensor' => true,
                    'has_temperature_sensor' => true,
                    'has_humidity_sensor' => true,
                    'has_co2_sensor' => true,
                    'has_water_level_sensor' => true,
                    'has_flow_sensor' => true,
                ],
            ]
        );

        $this->command->info("✓ Zone created: {$zone->id} (uid: {$zone->uid})");

        // 3. Создаем узел с UID из node-sim-config.yaml
        $node = DeviceNode::firstOrCreate(
            [
                'zone_id' => $zone->id,
                'uid' => 'nd-ph-esp32una',
            ],
            [
                'hardware_id' => 'esp32-test-001',
                'type' => 'ph',
                'name' => 'E2E Test PH Node',
                'status' => 'online',
                'lifecycle_state' => 'ASSIGNED_TO_ZONE',
                'last_seen_at' => Carbon::now(),
                'config' => [
                    'sensors' => ['ph_sensor', 'ec_sensor', 'solution_temp_c', 'air_temp_c', 'air_rh'],
                    'actuators' => ['main_pump', 'drain_pump', 'fan', 'heater', 'light', 'mister'],
                ],
            ]
        );
        // Приводим ноду к ожидаемому состоянию при повторных прогонах сидера.
        $node->status = 'online';
        $node->lifecycle_state = 'ASSIGNED_TO_ZONE';
        $node->last_seen_at = Carbon::now();
        $node->save();

        $this->command->info("✓ Node created: {$node->id} (uid: {$node->uid})");

        // 4. Создаем каналы для узла
        $channels = [
            ['channel' => 'ph_sensor', 'metric' => 'PH', 'unit' => 'pH', 'type' => 'sensor', 'data_type' => 'float'],
            ['channel' => 'ec_sensor', 'metric' => 'EC', 'unit' => 'mS/cm', 'type' => 'sensor', 'data_type' => 'float'],
            ['channel' => 'solution_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C', 'type' => 'sensor', 'data_type' => 'float'],
            ['channel' => 'air_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C', 'type' => 'sensor', 'data_type' => 'float'],
            ['channel' => 'air_rh', 'metric' => 'HUMIDITY', 'unit' => '%', 'type' => 'sensor', 'data_type' => 'float'],
        ];

        foreach ($channels as $channelData) {
            NodeChannel::firstOrCreate(
                [
                    'node_id' => $node->id,
                    'channel' => $channelData['channel'],
                ],
                [
                    'type' => $channelData['type'],
                    'metric' => $channelData['metric'],
                    'unit' => $channelData['unit'],
                    'config' => ['data_type' => $channelData['data_type']],
                ]
            );
        }

        $this->command->info('✓ Channels created for node');

        // 5. Создаем actuators (каналы типа actuator)
        $actuators = [
            ['channel' => 'main_pump', 'metric' => 'RELAY', 'unit' => 'bool', 'type' => 'actuator', 'data_type' => 'boolean'],
            ['channel' => 'drain_pump', 'metric' => 'RELAY', 'unit' => 'bool', 'type' => 'actuator', 'data_type' => 'boolean'],
            ['channel' => 'fan', 'metric' => 'RELAY', 'unit' => 'bool', 'type' => 'actuator', 'data_type' => 'boolean'],
            ['channel' => 'heater', 'metric' => 'RELAY', 'unit' => 'bool', 'type' => 'actuator', 'data_type' => 'boolean'],
            ['channel' => 'light', 'metric' => 'RELAY', 'unit' => 'bool', 'type' => 'actuator', 'data_type' => 'boolean'],
            ['channel' => 'mister', 'metric' => 'RELAY', 'unit' => 'bool', 'type' => 'actuator', 'data_type' => 'boolean'],
        ];
        $zoneRoles = [
            'main_pump' => 'main_pump',
            'drain_pump' => 'drain',
            'fan' => 'fan',
            'heater' => 'heater',
            'light' => 'light',
            'mister' => 'mist',
        ];

        foreach ($actuators as $actuatorData) {
            NodeChannel::updateOrCreate(
                [
                    'node_id' => $node->id,
                    'channel' => $actuatorData['channel'],
                ],
                [
                    'type' => $actuatorData['type'],
                    'metric' => $actuatorData['metric'],
                    'unit' => $actuatorData['unit'],
                    'config' => [
                        'data_type' => $actuatorData['data_type'],
                        'zone_role' => $zoneRoles[$actuatorData['channel']] ?? $actuatorData['channel'],
                    ],
                ]
            );
        }

        $this->command->info('✓ Actuators created for node');

        // 6. Создаем инфраструктуру зоны
        $infrastructure = [
            ['asset_type' => 'PUMP', 'channel' => 'main_pump', 'label' => 'Main Pump', 'required' => true, 'role' => 'main_pump'],
            ['asset_type' => 'DRAIN', 'channel' => 'drain_pump', 'label' => 'Drain Pump', 'required' => false, 'role' => 'drain'],
            ['asset_type' => 'FAN', 'channel' => 'fan', 'label' => 'Fan', 'required' => true, 'role' => 'fan'],
            ['asset_type' => 'HEATER', 'channel' => 'heater', 'label' => 'Heater', 'required' => true, 'role' => 'heater'],
            ['asset_type' => 'LIGHT', 'channel' => 'light', 'label' => 'Light', 'required' => false, 'role' => 'light'],
            ['asset_type' => 'MISTER', 'channel' => 'mister', 'label' => 'Mister', 'required' => false, 'role' => 'mister'],
        ];

        foreach ($infrastructure as $infraData) {
            $infra = InfrastructureInstance::firstOrCreate(
                [
                    'owner_type' => 'zone',
                    'owner_id' => $zone->id,
                    'asset_type' => $infraData['asset_type'],
                    'label' => $infraData['label'],
                ],
                [
                    'required' => $infraData['required'],
                ]
            );

            $channelName = $infraData['channel'] ?? null;
            $channel = $channelName
                ? NodeChannel::where('node_id', $node->id)
                    ->where('channel', $channelName)
                    ->first()
                : null;

            if ($channel) {
                $direction = $channel->type === 'actuator' ? 'actuator' : 'sensor';

                ChannelBinding::updateOrCreate(
                    [
                        'node_channel_id' => $channel->id,
                    ],
                    [
                        'infrastructure_instance_id' => $infra->id,
                        'direction' => $direction,
                        'role' => $infraData['role'] ?? $channel->channel,
                    ]
                );
            }
        }

        $this->command->info('✓ Infrastructure and bindings created');

        // 7. Создаем рецепт и ревизию с фазами
        $recipe = Recipe::firstOrCreate(
            ['name' => 'E2E Test Recipe'],
            [
                'description' => 'Recipe for E2E automation engine tests',
            ]
        );

        $plant = Plant::firstOrCreate([
            'name' => 'E2E Test Plant',
            'slug' => 'e2e-test-plant',
        ]);

        $recipe->plants()->syncWithoutDetaching([$plant->id]);

        $creatorId = User::where('role', 'admin')->value('id') ?? User::value('id');

        $revision = RecipeRevision::firstOrCreate([
            'recipe_id' => $recipe->id,
            'revision_number' => 1,
        ], [
            'status' => 'PUBLISHED',
            'description' => 'E2E baseline revision',
            'created_by' => $creatorId,
            'published_at' => now(),
        ]);

        $germinationTemplate = GrowStageTemplate::firstOrCreate([
            'code' => 'GERMINATION',
        ], [
            'name' => 'Проращивание',
            'order_index' => 0,
            'default_duration_days' => 3,
            'ui_meta' => ['color' => '#CDDC39', 'icon' => 'sprout'],
        ]);

        $vegTemplate = GrowStageTemplate::firstOrCreate([
            'code' => 'VEG',
        ], [
            'name' => 'Вегетация',
            'order_index' => 1,
            'default_duration_days' => 14,
            'ui_meta' => ['color' => '#2196F3', 'icon' => 'leaf'],
        ]);

        RecipeRevisionPhase::firstOrCreate(
            [
                'recipe_revision_id' => $revision->id,
                'phase_index' => 0,
            ],
            [
                'stage_template_id' => $germinationTemplate->id,
                'name' => 'Germination',
                'duration_hours' => 72,
                'ph_target' => 6.0,
                'ph_min' => 5.8,
                'ph_max' => 6.2,
                'ec_target' => 1.0,
                'ec_min' => 0.8,
                'ec_max' => 1.2,
                'temp_air_target' => 22.0,
                'humidity_target' => 70.0,
            ]
        );

        RecipeRevisionPhase::firstOrCreate(
            [
                'recipe_revision_id' => $revision->id,
                'phase_index' => 1,
            ],
            [
                'stage_template_id' => $vegTemplate->id,
                'name' => 'Growth',
                'duration_hours' => 336,
                'ph_target' => 6.0,
                'ph_min' => 5.5,
                'ph_max' => 6.5,
                'ec_target' => 1.5,
                'ec_min' => 1.2,
                'ec_max' => 1.8,
                'temp_air_target' => 24.0,
                'humidity_target' => 65.0,
            ]
        );

        $this->command->info('✓ Recipe revision and phases created');

        // 8. Создаем активный grow-cycle (если еще нет)
        $existingCycle = GrowCycle::where('zone_id', $zone->id)
            ->whereIn('status', ['PLANNED', 'RUNNING', 'PAUSED'])
            ->orderByDesc('created_at')
            ->first();

        if ($existingCycle) {
            $growCycle = $existingCycle;
            $this->command->info("✓ Grow cycle already exists: {$growCycle->id}");
        } else {
            $service = app(GrowCycleService::class);
            $growCycle = $service->createCycle($zone, $revision, $plant->id, [
                'start_immediately' => true,
                'planting_at' => Carbon::now()->subDays(5),
            ]);

            $this->command->info("✓ Grow cycle created: {$growCycle->id}");
        }

        $this->command->info('=== E2E Automation Engine seed completed ===');
        $this->command->info("Zone ID: {$zone->id}");
        $this->command->info("Zone UID: {$zone->uid}");
        $this->command->info("Node UID: {$node->uid}");
        $this->command->info("Recipe ID: {$recipe->id}");
        $this->command->info("Grow Cycle ID: {$growCycle->id}");
    }
}
