<?php

namespace Database\Seeders;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneLogicProfileCatalog;
use App\Services\ZoneLogicProfileService;
use App\Support\Automation\ZonePidDefaults;
use Carbon\Carbon;
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
        $this->seedAuthorityDocuments($zone);
        $this->seedPidConfigs($zone->id);
        $this->seedPredictionTelemetry($zone, $node);
        $this->pruneToSingleTopology($greenhouse->id, $zone->id, $node->id);
        $this->call(AccessControlBootstrapSeeder::class);

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
                'capabilities' => [
                    'ph_control' => true,
                    'ec_control' => true,
                    'climate_control' => true,
                    'light_control' => true,
                    'irrigation_control' => true,
                    'recirculation' => true,
                    'flow_sensor' => true,
                ],
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
        $documents = app(AutomationConfigDocumentService::class);

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            ZonePidDefaults::forType('ph'),
            $adminId ? (int) $adminId : null,
            'single_zone_service_seed'
        );

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            ZonePidDefaults::forType('ec'),
            $adminId ? (int) $adminId : null,
            'single_zone_service_seed'
        );
    }

    private function seedAuthorityDocuments(Zone $zone): void
    {
        $adminId = User::query()->where('role', 'admin')->value('id') ?? User::query()->value('id');
        $documents = app(AutomationConfigDocumentService::class);

        $documents->ensureSystemDefaults();
        $documents->ensureZoneDefaults((int) $zone->id);

        app(ZoneLogicProfileService::class)->upsertProfile(
            zone: $zone,
            mode: ZoneLogicProfileCatalog::MODE_WORKING,
            subsystems: $this->defaultAutomationSubsystems(),
            activate: true,
            userId: $adminId ? (int) $adminId : null,
        );
    }

    /**
     * @return array<string, mixed>
     */
    private function defaultAutomationSubsystems(): array
    {
        return [
            'diagnostics' => [
                'enabled' => true,
                'execution' => [
                    'workflow' => 'cycle_start',
                    'topology' => 'two_tank_drip_substrate_trays',
                ],
            ],
        ];
    }

    private function pruneToSingleTopology(int $greenhouseId, int $zoneId, int $nodeId): void
    {
        DB::transaction(function () use ($greenhouseId, $zoneId, $nodeId): void {
            DeviceNode::query()->where('id', '!=', $nodeId)->delete();
            Zone::query()->where('id', '!=', $zoneId)->delete();
            Greenhouse::query()->where('id', '!=', $greenhouseId)->delete();
        });
    }

    private function seedPredictionTelemetry(Zone $zone, DeviceNode $node): void
    {
        $sensor = Sensor::query()->updateOrCreate(
            [
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'scope' => 'inside',
                'type' => 'PH',
                'label' => 'ph_sensor',
            ],
            [
                'greenhouse_id' => $zone->greenhouse_id,
                'unit' => 'pH',
                'specs' => ['seeded_by' => 'SingleZoneServiceSeeder'],
                'is_active' => true,
                'last_read_at' => now(),
            ]
        );

        $baseTime = Carbon::now()->subMinutes(75);
        $values = [5.92, 5.98, 6.03, 6.08];

        foreach ($values as $index => $value) {
            $ts = $baseTime->copy()->addMinutes($index * 25);

            TelemetrySample::query()->updateOrCreate(
                [
                    'sensor_id' => $sensor->id,
                    'ts' => $ts,
                ],
                [
                    'zone_id' => $zone->id,
                    'cycle_id' => null,
                    'value' => $value,
                    'quality' => 'GOOD',
                    'metadata' => ['source' => 'single-zone-seeder'],
                ]
            );
        }

        TelemetryLast::query()->updateOrCreate(
            ['sensor_id' => $sensor->id],
            [
                'last_value' => end($values),
                'last_ts' => $baseTime->copy()->addMinutes((count($values) - 1) * 25),
                'last_quality' => 'GOOD',
            ]
        );
    }
}
