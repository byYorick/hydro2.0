<?php

namespace Database\Seeders;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\GrowStageTemplate;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Carbon\Carbon;
use Illuminate\Database\Seeder;

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
            ]
        );

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
                'greenhouse_id' => $greenhouse->id,
                'hardware_id' => 'esp32-test-001',
                'type' => 'ph',
                'name' => 'E2E Test PH Node',
                'status' => 'online',
                'last_seen_at' => Carbon::now(),
            ]
        );

        $this->command->info("✓ Node created: {$node->id} (uid: {$node->uid})");

        // 4. Создаем каналы для узла
        $channels = [
            ['name' => 'ph_sensor', 'metric_type' => 'PH', 'unit' => 'pH', 'data_type' => 'float'],
            ['name' => 'ec_sensor', 'metric_type' => 'EC', 'unit' => 'mS/cm', 'data_type' => 'float'],
            ['name' => 'air_temp_c', 'metric_type' => 'TEMP_AIR', 'unit' => '°C', 'data_type' => 'float'],
            ['name' => 'air_rh', 'metric_type' => 'HUMIDITY_AIR', 'unit' => '%', 'data_type' => 'float'],
            ['name' => 'solution_temp_c', 'metric_type' => 'TEMP_SOLUTION', 'unit' => '°C', 'data_type' => 'float'],
            ['name' => 'co2_ppm', 'metric_type' => 'CO2', 'unit' => 'ppm', 'data_type' => 'float'],
            ['name' => 'water_level', 'metric_type' => 'WATER_LEVEL', 'unit' => 'cm', 'data_type' => 'float'],
            ['name' => 'flow_rate', 'metric_type' => 'FLOW_RATE', 'unit' => 'L/min', 'data_type' => 'float'],
        ];

        foreach ($channels as $channelData) {
            NodeChannel::firstOrCreate(
                [
                    'node_id' => $node->id,
                    'name' => $channelData['name'],
                ],
                array_merge($channelData, [
                    'zone_id' => $zone->id,
                ])
            );
        }

        $this->command->info('✓ Channels created for node');

        // 5. Создаем actuators (каналы типа actuator)
        $actuators = [
            ['name' => 'main_pump', 'metric_type' => null, 'unit' => null, 'data_type' => 'boolean'],
            ['name' => 'drain_pump', 'metric_type' => null, 'unit' => null, 'data_type' => 'boolean'],
            ['name' => 'fan', 'metric_type' => null, 'unit' => null, 'data_type' => 'boolean'],
            ['name' => 'heater', 'metric_type' => null, 'unit' => null, 'data_type' => 'boolean'],
            ['name' => 'light', 'metric_type' => null, 'unit' => null, 'data_type' => 'boolean'],
            ['name' => 'mister', 'metric_type' => null, 'unit' => null, 'data_type' => 'boolean'],
            ['name' => 'ph_doser', 'metric_type' => null, 'unit' => null, 'data_type' => 'boolean'],
            ['name' => 'ec_doser', 'metric_type' => null, 'unit' => null, 'data_type' => 'boolean'],
        ];

        foreach ($actuators as $actuatorData) {
            NodeChannel::firstOrCreate(
                [
                    'node_id' => $node->id,
                    'name' => $actuatorData['name'],
                ],
                array_merge($actuatorData, [
                    'zone_id' => $zone->id,
                    'channel_type' => 'actuator',
                ])
            );
        }

        $this->command->info('✓ Actuators created for node');

        // 6. Создаем инфраструктуру зоны
        $infrastructure = [
            ['asset_type' => 'ph_sensor', 'label' => 'pH Sensor', 'required' => true],
            ['asset_type' => 'ec_sensor', 'label' => 'EC Sensor', 'required' => true],
            ['asset_type' => 'temperature_sensor', 'label' => 'Temperature Sensor', 'required' => true],
            ['asset_type' => 'humidity_sensor', 'label' => 'Humidity Sensor', 'required' => true],
            ['asset_type' => 'co2_sensor', 'label' => 'CO2 Sensor', 'required' => false],
            ['asset_type' => 'water_level_sensor', 'label' => 'Water Level Sensor', 'required' => true],
            ['asset_type' => 'flow_sensor', 'label' => 'Flow Sensor', 'required' => false],
            ['asset_type' => 'ph_doser', 'label' => 'pH Doser', 'required' => true],
            ['asset_type' => 'ec_doser', 'label' => 'EC Doser', 'required' => true],
            ['asset_type' => 'heater', 'label' => 'Heater', 'required' => true],
            ['asset_type' => 'fan', 'label' => 'Fan', 'required' => true],
            ['asset_type' => 'light', 'label' => 'Light', 'required' => false],
            ['asset_type' => 'main_pump', 'label' => 'Main Pump', 'required' => true],
            ['asset_type' => 'drain_pump', 'label' => 'Drain Pump', 'required' => false],
        ];

        foreach ($infrastructure as $infraData) {
            $infra = InfrastructureInstance::firstOrCreate(
                [
                    'owner_type' => 'zone',
                    'owner_id' => $zone->id,
                    'asset_type' => $infraData['asset_type'],
                ],
                [
                    'label' => $infraData['label'],
                    'required' => $infraData['required'],
                ]
            );

            if ($infraData['required']) {
                $channel = NodeChannel::where('node_id', $node->id)
                    ->where('name', $infraData['asset_type'])
                    ->first();

                if ($channel) {
                    $direction = in_array($infraData['asset_type'], ['ph_sensor', 'ec_sensor', 'temperature_sensor', 'humidity_sensor', 'co2_sensor', 'water_level_sensor', 'flow_sensor'])
                        ? 'sensor'
                        : 'actuator';

                    ChannelBinding::firstOrCreate(
                        [
                            'infrastructure_instance_id' => $infra->id,
                            'node_channel_id' => $channel->id,
                        ],
                        [
                            'direction' => $direction,
                            'role' => $infraData['asset_type'],
                        ]
                    );
                }
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

        $revision = RecipeRevision::firstOrCreate([
            'recipe_id' => $recipe->id,
            'revision_number' => 1,
        ], [
            'status' => 'PUBLISHED',
            'description' => 'E2E baseline revision',
            'created_by' => 1,
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

        // 8. Создаем активный grow-cycle
        $service = app(GrowCycleService::class);
        $growCycle = $service->createCycle($zone, $revision, $plant->id, [
            'start_immediately' => true,
            'planting_at' => Carbon::now()->subDays(5),
        ]);

        $this->command->info("✓ Grow cycle created: {$growCycle->id}");

        $this->command->info('=== E2E Automation Engine seed completed ===');
        $this->command->info("Zone ID: {$zone->id}");
        $this->command->info("Zone UID: {$zone->uid}");
        $this->command->info("Node UID: {$node->uid}");
        $this->command->info("Recipe ID: {$recipe->id}");
        $this->command->info("Grow Cycle ID: {$growCycle->id}");
    }
}
