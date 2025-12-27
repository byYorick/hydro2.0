<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Recipe;
use App\Models\RecipePhase;
use App\Models\ZoneRecipeInstance;
use App\Models\GrowCycle;
use App\Models\GrowCycleStage;
use App\Models\ZoneInfrastructure;
use App\Models\ZoneChannelBinding;
use Carbon\Carbon;
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

        $this->command->info("✓ Channels created for node");

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

        $this->command->info("✓ Actuators created for node");

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
            $infra = ZoneInfrastructure::firstOrCreate(
                [
                    'zone_id' => $zone->id,
                    'asset_type' => $infraData['asset_type'],
                ],
                array_merge($infraData, [
                    'role' => $infraData['asset_type'],
                ])
            );

            // Создаем bindings для required инфраструктуры
            if ($infraData['required']) {
                $channel = NodeChannel::where('node_id', $node->id)
                    ->where('name', $infraData['asset_type'])
                    ->first();

                if ($channel) {
                    $direction = in_array($infraData['asset_type'], ['ph_sensor', 'ec_sensor', 'temperature_sensor', 'humidity_sensor', 'co2_sensor', 'water_level_sensor', 'flow_sensor']) 
                        ? 'sensor' 
                        : 'actuator';
                    
                    ZoneChannelBinding::firstOrCreate(
                        [
                            'zone_id' => $zone->id,
                            'asset_id' => $infra->id,
                            'node_id' => $node->id,
                            'channel' => $channel->name,
                        ],
                        [
                            'direction' => $direction,
                            'role' => $infraData['asset_type'],
                        ]
                    );
                }
            }
        }

        $this->command->info("✓ Infrastructure and bindings created");

        // 7. Создаем рецепт с фазами
        $recipe = Recipe::firstOrCreate(
            ['name' => 'E2E Test Recipe'],
            [
                'description' => 'Recipe for E2E automation engine tests',
                'crop_type' => 'lettuce',
                'duration_days' => 30,
            ]
        );

        // Фаза 1: Germination
        $phase1 = RecipePhase::firstOrCreate(
            [
                'recipe_id' => $recipe->id,
                'phase_index' => 0,
            ],
            [
                'name' => 'Germination',
                'duration_hours' => 72,
                'targets' => [
                    'ph' => ['min' => 5.8, 'max' => 6.2, 'target' => 6.0],
                    'ec' => ['min' => 0.8, 'max' => 1.2, 'target' => 1.0],
                    'air_temp_c' => ['min' => 20.0, 'max' => 24.0, 'target' => 22.0],
                    'air_rh' => ['min' => 60.0, 'max' => 80.0, 'target' => 70.0],
                    'co2_ppm' => ['min' => 400.0, 'max' => 800.0, 'target' => 600.0],
                ],
            ]
        );

        // Фаза 2: Growth
        $phase2 = RecipePhase::firstOrCreate(
            [
                'recipe_id' => $recipe->id,
                'phase_index' => 1,
            ],
            [
                'name' => 'Growth',
                'duration_hours' => 336, // 14 days
                'targets' => [
                    'ph' => ['min' => 5.5, 'max' => 6.5, 'target' => 6.0],
                    'ec' => ['min' => 1.2, 'max' => 1.8, 'target' => 1.5],
                    'air_temp_c' => ['min' => 22.0, 'max' => 26.0, 'target' => 24.0],
                    'air_rh' => ['min' => 55.0, 'max' => 75.0, 'target' => 65.0],
                    'co2_ppm' => ['min' => 400.0, 'max' => 1000.0, 'target' => 800.0],
                ],
            ]
        );

        $this->command->info("✓ Recipe and phases created");

        // 8. Создаем экземпляр рецепта в зоне
        $recipeInstance = ZoneRecipeInstance::firstOrCreate(
            ['zone_id' => $zone->id],
            [
                'recipe_id' => $recipe->id,
                'current_phase_index' => 1, // Активная фаза Growth
                'started_at' => Carbon::now()->subDays(5),
            ]
        );

        $this->command->info("✓ Recipe instance created (phase: {$recipeInstance->current_phase_index})");

        // 9. Создаем активный grow-cycle со стадиями
        $growCycle = GrowCycle::firstOrCreate(
            [
                'zone_id' => $zone->id,
                'status' => 'RUNNING',
            ],
            [
                'greenhouse_id' => $greenhouse->id,
                'recipe_id' => $recipe->id,
                'started_at' => Carbon::now()->subDays(5),
                'planned_harvest_at' => Carbon::now()->addDays(25),
            ]
        );

        // Создаем стадии для grow-cycle
        $stages = [
            [
                'stage_index' => 0,
                'name' => 'Germination',
                'started_at' => Carbon::now()->subDays(5),
                'planned_duration_hours' => 72,
                'targets_override' => [
                    'ph' => ['min' => 5.8, 'max' => 6.2, 'target' => 6.0],
                    'ec' => ['min' => 0.8, 'max' => 1.2, 'target' => 1.0],
                    'air_temp_c' => ['min' => 20.0, 'max' => 24.0, 'target' => 22.0],
                ],
            ],
            [
                'stage_index' => 1,
                'name' => 'Growth',
                'started_at' => Carbon::now()->subDays(2),
                'planned_duration_hours' => 336,
                'targets_override' => [
                    'ph' => ['min' => 5.5, 'max' => 6.5, 'target' => 6.0],
                    'ec' => ['min' => 1.2, 'max' => 1.8, 'target' => 1.5],
                    'air_temp_c' => ['min' => 22.0, 'max' => 26.0, 'target' => 24.0],
                ],
            ],
        ];

        foreach ($stages as $stageData) {
            GrowCycleStage::firstOrCreate(
                [
                    'grow_cycle_id' => $growCycle->id,
                    'stage_index' => $stageData['stage_index'],
                ],
                $stageData
            );
        }

        $this->command->info("✓ Grow cycle and stages created");

        $this->command->info("=== E2E Automation Engine seed completed ===");
        $this->command->info("Zone ID: {$zone->id}");
        $this->command->info("Zone UID: {$zone->uid}");
        $this->command->info("Node UID: {$node->uid}");
        $this->command->info("Recipe ID: {$recipe->id}");
        $this->command->info("Grow Cycle ID: {$growCycle->id}");
    }
}

