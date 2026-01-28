<?php

namespace Database\Seeders;

use App\Models\Alert;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Preset;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Carbon\Carbon;
use Illuminate\Database\Seeder;

class DemoDataSeeder extends Seeder
{
    public function run(): void
    {
        // Create or get greenhouse
        $greenhouse = Greenhouse::firstOrCreate(
            ['uid' => 'gh-main-001'],
            [
                'name' => 'Main Greenhouse',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'coordinates' => ['lat' => 55.7558, 'lon' => 37.6173],
                'description' => 'Main production greenhouse',
            ]
        );

        // Create or get zones
        $zone1 = Zone::firstOrCreate(
            ['greenhouse_id' => $greenhouse->id, 'name' => 'Zone A - Lettuce'],
            [
                'description' => 'Lettuce production zone',
                'status' => 'RUNNING',
            ]
        );

        $zone2 = Zone::firstOrCreate(
            ['greenhouse_id' => $greenhouse->id, 'name' => 'Zone B - Basil'],
            [
                'description' => 'Basil production zone',
                'status' => 'PAUSED',
            ]
        );

        $zone3 = Zone::firstOrCreate(
            ['greenhouse_id' => $greenhouse->id, 'name' => 'Zone C - Tomatoes'],
            [
                'description' => 'Tomato seedlings zone',
                'status' => 'RUNNING',
            ]
        );

        // Create or get nodes for Zone A
        $node1 = DeviceNode::firstOrCreate(
            ['uid' => 'nd-ph-001'],
            [
                'zone_id' => $zone1->id,
                'name' => 'pH Sensor Node',
                'type' => 'sensor',
                'fw_version' => '1.2.3',
                'last_seen_at' => Carbon::now()->subMinutes(2),
                'status' => 'online',
                'config' => ['interval' => 60],
            ]
        );

        NodeChannel::firstOrCreate(
            ['node_id' => $node1->id, 'channel' => 'ph'],
            [
                'type' => 'sensor',
                'metric' => 'pH',
                'unit' => 'pH',
                'config' => ['min' => 0, 'max' => 14],
            ]
        );

        NodeChannel::firstOrCreate(
            ['node_id' => $node1->id, 'channel' => 'pump_acid'],
            [
                'type' => 'actuator',
                'metric' => 'Pump',
                'unit' => 'bool',
                'config' => ['default' => false],
            ]
        );

        $node2 = DeviceNode::firstOrCreate(
            ['uid' => 'nd-ec-001'],
            [
                'zone_id' => $zone1->id,
                'name' => 'EC Sensor Node',
                'type' => 'sensor',
                'fw_version' => '1.1.5',
                'last_seen_at' => Carbon::now()->subMinutes(1),
                'status' => 'online',
                'config' => ['interval' => 60],
            ]
        );

        NodeChannel::firstOrCreate(
            ['node_id' => $node2->id, 'channel' => 'ec'],
            [
                'type' => 'sensor',
                'metric' => 'EC',
                'unit' => 'mS/cm',
                'config' => ['min' => 0, 'max' => 5],
            ]
        );

        // Create or get nodes for Zone B
        $node3 = DeviceNode::firstOrCreate(
            ['uid' => 'nd-temp-001'],
            [
                'zone_id' => $zone2->id,
                'name' => 'Temperature Sensor',
                'type' => 'sensor',
                'fw_version' => '1.0.8',
                'last_seen_at' => Carbon::now()->subHours(1),
                'status' => 'offline',
                'config' => ['interval' => 120],
            ]
        );

        NodeChannel::firstOrCreate(
            ['node_id' => $node3->id, 'channel' => 'temperature'],
            [
                'type' => 'sensor',
                'metric' => 'Temperature',
                'unit' => '°C',
                'config' => ['min' => -10, 'max' => 50],
            ]
        );

        // Create or get nodes for Zone C
        $node4 = DeviceNode::firstOrCreate(
            ['uid' => 'nd-combo-001'],
            [
                'zone_id' => $zone3->id,
                'name' => 'Combo Sensor Node',
                'type' => 'sensor',
                'fw_version' => '2.0.1',
                'last_seen_at' => Carbon::now()->subMinutes(5),
                'status' => 'online',
                'config' => ['interval' => 30],
            ]
        );

        NodeChannel::firstOrCreate(
            ['node_id' => $node4->id, 'channel' => 'ph'],
            [
                'type' => 'sensor',
                'metric' => 'pH',
                'unit' => 'pH',
                'config' => ['min' => 0, 'max' => 14],
            ]
        );

        NodeChannel::firstOrCreate(
            ['node_id' => $node4->id, 'channel' => 'ec'],
            [
                'type' => 'sensor',
                'metric' => 'EC',
                'unit' => 'mS/cm',
                'config' => ['min' => 0, 'max' => 5],
            ]
        );

        NodeChannel::firstOrCreate(
            ['node_id' => $node4->id, 'channel' => 'temperature'],
            [
                'type' => 'sensor',
                'metric' => 'Temperature',
                'unit' => '°C',
                'config' => ['min' => -10, 'max' => 50],
            ]
        );

        $creatorId = User::query()->value('id');
        $growCycleService = app(GrowCycleService::class);

        // Create or get plants
        $lettucePlant = Plant::firstOrCreate(
            ['slug' => 'lettuce-demo'],
            [
                'name' => 'Lettuce',
                'species' => 'Lactuca sativa',
            ]
        );

        $basilPlant = Plant::firstOrCreate(
            ['slug' => 'basil-demo'],
            [
                'name' => 'Basil',
                'species' => 'Ocimum basilicum',
            ]
        );

        // Create or get recipes
        $recipe1 = Recipe::firstOrCreate(
            ['name' => 'Lettuce Standard'],
            ['description' => 'Standard lettuce growing recipe']
        );

        $recipe1->plants()->syncWithoutDetaching([
            $lettucePlant->id => ['is_default' => true],
        ]);

        $revision1 = RecipeRevision::firstOrCreate(
            ['recipe_id' => $recipe1->id, 'revision_number' => 1],
            [
                'status' => 'PUBLISHED',
                'description' => 'Initial revision',
                'created_by' => $creatorId,
                'published_at' => now(),
            ]
        );

        $phases1 = [
            ['phase_index' => 0, 'name' => 'seedling', 'duration_hours' => 240, 'ph_min' => 5.6, 'ph_max' => 5.9, 'ec_min' => 1.2, 'ec_max' => 1.4],
            ['phase_index' => 1, 'name' => 'veg', 'duration_hours' => 480, 'ph_min' => 5.7, 'ph_max' => 6.0, 'ec_min' => 1.4, 'ec_max' => 1.8],
        ];

        foreach ($phases1 as $phaseData) {
            $phTarget = ($phaseData['ph_min'] + $phaseData['ph_max']) / 2;
            $ecTarget = ($phaseData['ec_min'] + $phaseData['ec_max']) / 2;

            RecipeRevisionPhase::firstOrCreate(
                [
                    'recipe_revision_id' => $revision1->id,
                    'phase_index' => $phaseData['phase_index'],
                ],
                [
                    'name' => $phaseData['name'],
                    'duration_hours' => $phaseData['duration_hours'],
                    'ph_min' => $phaseData['ph_min'],
                    'ph_max' => $phaseData['ph_max'],
                    'ph_target' => $phTarget,
                    'ec_min' => $phaseData['ec_min'],
                    'ec_max' => $phaseData['ec_max'],
                    'ec_target' => $ecTarget,
                ]
            );
        }

        $recipe2 = Recipe::firstOrCreate(
            ['name' => 'Basil Fast'],
            ['description' => 'Fast-growing basil recipe']
        );

        $recipe2->plants()->syncWithoutDetaching([
            $basilPlant->id => ['is_default' => true],
        ]);

        $revision2 = RecipeRevision::firstOrCreate(
            ['recipe_id' => $recipe2->id, 'revision_number' => 1],
            [
                'status' => 'PUBLISHED',
                'description' => 'Initial revision',
                'created_by' => $creatorId,
                'published_at' => now(),
            ]
        );

        $phases2 = [
            ['phase_index' => 0, 'name' => 'seedling', 'duration_hours' => 168, 'ph_min' => 5.8, 'ph_max' => 6.2, 'ec_min' => 1.0, 'ec_max' => 1.3],
            ['phase_index' => 1, 'name' => 'growth', 'duration_hours' => 336, 'ph_min' => 6.0, 'ph_max' => 6.5, 'ec_min' => 1.3, 'ec_max' => 1.6],
        ];

        foreach ($phases2 as $phaseData) {
            $phTarget = ($phaseData['ph_min'] + $phaseData['ph_max']) / 2;
            $ecTarget = ($phaseData['ec_min'] + $phaseData['ec_max']) / 2;

            RecipeRevisionPhase::firstOrCreate(
                [
                    'recipe_revision_id' => $revision2->id,
                    'phase_index' => $phaseData['phase_index'],
                ],
                [
                    'name' => $phaseData['name'],
                    'duration_hours' => $phaseData['duration_hours'],
                    'ph_min' => $phaseData['ph_min'],
                    'ph_max' => $phaseData['ph_max'],
                    'ph_target' => $phTarget,
                    'ec_min' => $phaseData['ec_min'],
                    'ec_max' => $phaseData['ec_max'],
                    'ec_target' => $ecTarget,
                ]
            );
        }

        // Link zones with presets
        $lettucePreset = Preset::where('name', 'Lettuce Standard')->first();
        $basilPreset = Preset::where('name', 'Basil/Herbs')->first();
        $tomatoPreset = Preset::where('name', 'Tomato/Cucumber')->first();

        if ($lettucePreset) {
            $zone1->preset_id = $lettucePreset->id;
            $zone1->save();
        }

        if ($basilPreset) {
            $zone2->preset_id = $basilPreset->id;
            $zone2->save();
        }

        if ($tomatoPreset) {
            $zone3->preset_id = $tomatoPreset->id;
            $zone3->save();
        }

        // Create grow cycles for zones
        $cycleConfigs = [
            [
                'zone' => $zone1,
                'recipe' => $recipe1,
                'plant' => $lettucePlant,
                'started_at' => Carbon::now()->subDays(5),
                'status' => 'RUNNING',
            ],
            [
                'zone' => $zone2,
                'recipe' => $recipe2,
                'plant' => $basilPlant,
                'started_at' => Carbon::now()->subDays(2),
                'status' => 'PAUSED',
            ],
            [
                'zone' => $zone3,
                'recipe' => $recipe1,
                'plant' => $lettucePlant,
                'started_at' => Carbon::now()->subDays(1),
                'status' => 'RUNNING',
            ],
        ];

        foreach ($cycleConfigs as $config) {
            /** @var Zone $zone */
            $zone = $config['zone'];

            if ($zone->activeGrowCycle) {
                continue;
            }

            $revision = RecipeRevision::query()
                ->where('recipe_id', $config['recipe']->id)
                ->where('status', 'PUBLISHED')
                ->orderByDesc('revision_number')
                ->first();

            if (! $revision) {
                continue;
            }

            $cycle = $growCycleService->createCycle(
                $zone,
                $revision,
                $config['plant']->id,
                [
                    'start_immediately' => true,
                    'planting_at' => $config['started_at'],
                ],
                $creatorId
            );

            if ($config['status'] === 'PAUSED' && $creatorId) {
                $growCycleService->pause($cycle, $creatorId);
            }
        }

        // Create alerts (only if they don't exist - skip duplicates)
        if (Alert::where('zone_id', $zone1->id)->where('type', 'ph_high')->where('status', 'active')->count() === 0) {
            Alert::create([
                'zone_id' => $zone1->id,
                'type' => 'ph_high',
                'status' => 'active',
                'details' => ['message' => 'pH level too high: 6.5', 'threshold' => 6.0, 'current' => 6.5],
                'created_at' => Carbon::now()->subMinutes(15),
            ]);
        }

        if (Alert::where('zone_id', $zone2->id)->where('type', 'node_offline')->where('status', 'active')->count() === 0) {
            Alert::create([
                'zone_id' => $zone2->id,
                'type' => 'node_offline',
                'status' => 'active',
                'details' => ['message' => 'Node nd-temp-001 is offline', 'node_uid' => 'nd-temp-001'],
                'created_at' => Carbon::now()->subHours(1),
            ]);
        }

        if (Alert::where('zone_id', $zone1->id)->where('type', 'ec_low')->where('status', 'resolved')->count() === 0) {
            Alert::create([
                'zone_id' => $zone1->id,
                'type' => 'ec_low',
                'status' => 'resolved',
                'details' => ['message' => 'EC level too low: 1.0', 'threshold' => 1.2, 'current' => 1.0],
                'created_at' => Carbon::now()->subHours(2),
                'resolved_at' => Carbon::now()->subHour(),
            ]);
        }

        if (Alert::where('zone_id', $zone3->id)->where('type', 'temp_high')->where('status', 'active')->count() === 0) {
            Alert::create([
                'zone_id' => $zone3->id,
                'type' => 'temp_high',
                'status' => 'active',
                'details' => ['message' => 'Temperature too high: 28°C', 'threshold' => 25, 'current' => 28],
                'created_at' => Carbon::now()->subMinutes(30),
            ]);
        }

        if (Alert::where('zone_id', $zone1->id)->where('type', 'config_error')->where('status', 'active')->count() === 0) {
            Alert::create([
                'zone_id' => $zone1->id,
                'type' => 'config_error',
                'status' => 'active',
                'details' => ['message' => 'Config mismatch on node nd-ph-001', 'node_uid' => 'nd-ph-001', 'expected_version' => '1.2.3', 'actual_version' => '1.2.2'],
                'created_at' => Carbon::now()->subMinutes(5),
            ]);
        }

        $this->command->info('Demo data seeded successfully!');
        $this->command->info('- 1 Greenhouse');
        $this->command->info('- 3 Zones (with presets)');
        $this->command->info('- 4 Nodes with 7 Channels');
        $this->command->info('- 2 Recipes with 2 revisions and 4 phases');
        $this->command->info('- 3 Active Grow Cycles');
        $this->command->info('- 5 Alerts');
    }
}
