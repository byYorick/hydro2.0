<?php

namespace Database\Seeders;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZonePidConfig;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Минимальный dev-профиль:
 * - 1 теплица (gh-test-1)
 * - 1 зона (zn-test-1)
 * - 1 узел (nd-ph-esp32una)
 *
 * Топология синхронизирована с tests/e2e/node-sim-config.yaml
 * и ожиданиями Python-сервисов.
 */
class SingleZoneServiceSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Single-zone service dataset ===');

        $this->call(AdminUserSeeder::class);
        $this->call(PresetSeeder::class);
        $this->call(AutomationEngineE2ESeeder::class);

        $greenhouse = Greenhouse::query()->where('uid', 'gh-test-1')->firstOrFail();
        $zone = Zone::query()->where('uid', 'zn-test-1')->firstOrFail();
        $node = DeviceNode::query()->where('uid', 'nd-ph-esp32una')->firstOrFail();

        $this->tuneZoneForServices($zone->id, $greenhouse->id);
        $this->seedPidConfigs($zone->id);
        $this->pruneToSingleTopology($greenhouse->id, $zone->id, $node->id);

        $this->command->info('=== Single-zone service dataset complete ===');
        $this->command->info("Greenhouse UID: {$greenhouse->uid}");
        $this->command->info("Zone UID: {$zone->uid}");
        $this->command->info("Node UID: {$node->uid}");
    }

    private function tuneZoneForServices(int $zoneId, int $greenhouseId): void
    {
        Zone::query()
            ->where('id', $zoneId)
            ->update([
                'greenhouse_id' => $greenhouseId,
                'status' => 'RUNNING',
                'health_status' => 'good',
                'health_score' => 90,
                'settings' => [
                    'ph_control' => ['strategy' => 'periodic', 'interval_sec' => 300],
                    'ec_control' => ['strategy' => 'periodic', 'interval_sec' => 300],
                    'irrigation' => ['strategy' => 'periodic', 'interval_sec' => 900],
                    'lighting' => ['strategy' => 'periodic', 'interval_sec' => 3600],
                    'climate' => ['strategy' => 'periodic', 'interval_sec' => 300],
                ],
            ]);

        DeviceNode::query()
            ->where('zone_id', $zoneId)
            ->update([
                'status' => 'online',
                'lifecycle_state' => 'ASSIGNED_TO_ZONE',
                'last_seen_at' => now(),
                'last_heartbeat_at' => now(),
            ]);
    }

    private function seedPidConfigs(int $zoneId): void
    {
        $adminId = User::query()->where('role', 'admin')->value('id') ?? User::query()->value('id');

        $common = [
            'dead_zone' => 0.1,
            'close_zone' => 0.2,
            'far_zone' => 0.5,
            'zone_coeffs' => [
                'close' => ['kp' => 0.30, 'ki' => 0.04, 'kd' => 0.02],
                'far' => ['kp' => 0.45, 'ki' => 0.06, 'kd' => 0.03],
            ],
            'max_output' => 100.0,
            'min_interval_ms' => 60000,
            'enable_autotune' => false,
            'adaptation_rate' => 0.02,
        ];

        ZonePidConfig::query()->updateOrCreate(
            ['zone_id' => $zoneId, 'type' => 'ph'],
            [
                'config' => array_merge($common, ['target' => 6.0]),
                'updated_by' => $adminId,
                'updated_at' => now(),
            ]
        );

        ZonePidConfig::query()->updateOrCreate(
            ['zone_id' => $zoneId, 'type' => 'ec'],
            [
                'config' => array_merge($common, ['target' => 1.5]),
                'updated_by' => $adminId,
                'updated_at' => now(),
            ]
        );
    }

    private function pruneToSingleTopology(int $greenhouseId, int $zoneId, int $nodeId): void
    {
        DB::transaction(function () use ($greenhouseId, $zoneId, $nodeId): void {
            DeviceNode::query()->where('id', '!=', $nodeId)->delete();
            Zone::query()->where('id', '!=', $zoneId)->delete();
            Greenhouse::query()->where('id', '!=', $greenhouseId)->delete();
        });
    }
}

