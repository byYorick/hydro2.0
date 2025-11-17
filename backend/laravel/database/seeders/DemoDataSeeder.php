<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Recipe;
use App\Models\RecipePhase;
use App\Models\Alert;
use Carbon\Carbon;

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

        // Create or get recipes
        $recipe1 = Recipe::firstOrCreate(
            ['name' => 'Lettuce Standard'],
            ['description' => 'Standard lettuce growing recipe']
        );

        RecipePhase::firstOrCreate(
            ['recipe_id' => $recipe1->id, 'phase_index' => 0],
            [
                'name' => 'seedling',
                'duration_hours' => 240, // 10 days
                'targets' => [
                    'ph' => ['min' => 5.6, 'max' => 5.9],
                    'ec' => ['min' => 1.2, 'max' => 1.4],
                ],
            ]
        );

        RecipePhase::firstOrCreate(
            ['recipe_id' => $recipe1->id, 'phase_index' => 1],
            [
                'name' => 'veg',
                'duration_hours' => 480, // 20 days
                'targets' => [
                    'ph' => ['min' => 5.7, 'max' => 6.0],
                    'ec' => ['min' => 1.4, 'max' => 1.8],
                ],
            ]
        );

        $recipe2 = Recipe::firstOrCreate(
            ['name' => 'Basil Fast'],
            ['description' => 'Fast-growing basil recipe']
        );

        RecipePhase::firstOrCreate(
            ['recipe_id' => $recipe2->id, 'phase_index' => 0],
            [
                'name' => 'seedling',
                'duration_hours' => 168, // 7 days
                'targets' => [
                    'ph' => ['min' => 5.8, 'max' => 6.2],
                    'ec' => ['min' => 1.0, 'max' => 1.3],
                ],
            ]
        );

        RecipePhase::firstOrCreate(
            ['recipe_id' => $recipe2->id, 'phase_index' => 1],
            [
                'name' => 'growth',
                'duration_hours' => 336, // 14 days
                'targets' => [
                    'ph' => ['min' => 6.0, 'max' => 6.5],
                    'ec' => ['min' => 1.3, 'max' => 1.6],
                ],
            ]
        );

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
        $this->command->info('- 3 Zones');
        $this->command->info('- 4 Nodes with 7 Channels');
        $this->command->info('- 2 Recipes with 4 Phases');
        $this->command->info('- 5 Alerts');
    }
}

