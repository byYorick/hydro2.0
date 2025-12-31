<?php

namespace Database\Seeders;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\NodeChannel;
use App\Models\Zone;
use Illuminate\Database\Seeder;

/**
 * Minimal deterministic dataset for E2E scenarios.
 *
 * Creates:
 * - greenhouse uid: gh-test-1
 * - zone uid:      zn-test-1
 * - node uid:      nd-ph-test-1 (hardware_id esp32-test-001)
 *
 * Keep in sync with tests/e2e/scenarios/*.yaml and tests/node_sim configs.
 */
class E2eDataSeeder extends Seeder
{
    public function run(): void
    {
        $gh = Greenhouse::updateOrCreate(
            ['uid' => 'gh-test-1'],
            [
                'name' => 'E2E Greenhouse',
                'timezone' => 'UTC',
                'type' => 'GREENHOUSE',
                'coordinates' => ['lat' => 0, 'lon' => 0],
                'description' => 'Deterministic greenhouse for E2E scenarios',
                'provisioning_token' => 'gh_e2e_test_gh-test-1',
            ]
        );

        $zone = Zone::updateOrCreate(
            ['uid' => 'zn-test-1'],
            [
                'greenhouse_id' => $gh->id,
                'name' => 'E2E Zone 1',
                'description' => 'Deterministic zone for E2E scenarios',
                'status' => 'offline',
            ]
        );

        $node = DeviceNode::updateOrCreate(
            ['uid' => 'nd-ph-test-1'],
            [
                'zone_id' => $zone->id,
                'name' => 'E2E Node (pH)',
                'type' => 'ph',
                'status' => 'offline',
                'fw_version' => 'e2e',
                'hardware_id' => 'esp32-test-001',
                'lifecycle_state' => 'ASSIGNED_TO_ZONE',
                'config' => [
                    'sensors' => ['ph', 'ec', 'solution_temp_c', 'air_temp_c', 'air_rh'],
                    'actuators' => ['main_pump', 'drain_pump', 'fan', 'heater', 'light', 'mister'],
                ],
            ]
        );

        $sensorChannels = [
            ['channel' => 'ph', 'type' => 'sensor', 'metric' => 'PH', 'unit' => 'pH'],
            ['channel' => 'ec', 'type' => 'sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
            ['channel' => 'solution_temp_c', 'type' => 'sensor', 'metric' => 'TEMPERATURE', 'unit' => 'C'],
            ['channel' => 'air_temp_c', 'type' => 'sensor', 'metric' => 'TEMPERATURE', 'unit' => 'C'],
            ['channel' => 'air_rh', 'type' => 'sensor', 'metric' => 'AIR_RH', 'unit' => '%'],
        ];

        $actuatorChannels = [
            ['channel' => 'main_pump', 'type' => 'actuator', 'metric' => 'RELAY', 'unit' => 'bool'],
            ['channel' => 'drain_pump', 'type' => 'actuator', 'metric' => 'RELAY', 'unit' => 'bool'],
            ['channel' => 'fan', 'type' => 'actuator', 'metric' => 'RELAY', 'unit' => 'bool'],
            ['channel' => 'heater', 'type' => 'actuator', 'metric' => 'RELAY', 'unit' => 'bool'],
            ['channel' => 'light', 'type' => 'actuator', 'metric' => 'RELAY', 'unit' => 'bool'],
            ['channel' => 'mister', 'type' => 'actuator', 'metric' => 'RELAY', 'unit' => 'bool'],
        ];

        foreach (array_merge($sensorChannels, $actuatorChannels) as $ch) {
            NodeChannel::updateOrCreate(
                ['node_id' => $node->id, 'channel' => $ch['channel']],
                [
                    'type' => $ch['type'],
                    'metric' => $ch['metric'],
                    'unit' => $ch['unit'],
                    'config' => $ch['config'] ?? [],
                ]
            );
        }
    }
}
