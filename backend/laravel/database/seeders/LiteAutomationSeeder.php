<?php

namespace Database\Seeders;

use App\Enums\GrowCycleStatus;
use App\Models\Alert;
use App\Models\ChannelBinding;
use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\GrowStageTemplate;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Preset;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\GrowCycleService;
use Carbon\Carbon;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

class LiteAutomationSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Lite Automation Engine dataset ===');

        $this->call(AdminUserSeeder::class);
        $this->call(PresetSeeder::class);

        $greenhouse = $this->createGreenhouse();
        $zones = $this->createZones($greenhouse);
        $nodes = $this->createNodesAndChannels($zones);

        $this->createInfrastructure($zones['running'], $nodes['running']);

        [$plant, $revision] = $this->createRecipe();
        $cycles = $this->createCycles($zones, $revision, $plant->id);

        $this->seedTelemetry($zones, $nodes, $cycles);
        $this->seedAutomationSignals($zones, $nodes, $cycles);

        $this->command->info('=== Lite Automation Engine seeding complete ===');
    }

    private function createGreenhouse(): Greenhouse
    {
        $greenhouse = Greenhouse::updateOrCreate(
            ['uid' => 'gh-lite-automation-1'],
            [
                'name' => 'Automation Lite Greenhouse',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'coordinates' => ['lat' => 55.7558, 'lon' => 37.6173],
                'description' => 'Lightweight dataset for automation engine testing',
                'provisioning_token' => 'gh_lite_'.Str::random(24),
            ]
        );

        if (! $greenhouse->provisioning_token) {
            $greenhouse->provisioning_token = 'gh_lite_'.Str::random(24);
            $greenhouse->save();
        }

        return $greenhouse;
    }

    /**
     * @return array{running: Zone, paused: Zone, planned: Zone, empty: Zone}
     */
    private function createZones(Greenhouse $greenhouse): array
    {
        $presetId = Preset::query()->value('id');

        $baseSettings = [
            'ph_control' => ['strategy' => 'periodic', 'interval_sec' => 300],
            'ec_control' => ['strategy' => 'periodic', 'interval_sec' => 300],
            'irrigation' => ['strategy' => 'periodic', 'interval_sec' => 900],
            'lighting' => ['strategy' => 'periodic', 'interval_sec' => 43200],
            'climate' => ['strategy' => 'periodic', 'interval_sec' => 300],
        ];

        $fullCapabilities = [
            'ph_control' => true,
            'ec_control' => true,
            'climate_control' => true,
            'light_control' => true,
            'irrigation_control' => true,
            'recirculation' => true,
            'flow_sensor' => true,
        ];

        $fullHardware = [
            'has_ph_sensor' => true,
            'has_ec_sensor' => true,
            'has_temperature_sensor' => true,
            'has_humidity_sensor' => true,
            'has_co2_sensor' => true,
            'has_water_level_sensor' => true,
            'has_flow_sensor' => true,
        ];

        $zones = [
            'running' => Zone::updateOrCreate(
                ['uid' => 'zn-lite-run-1'],
                [
                    'greenhouse_id' => $greenhouse->id,
                    'preset_id' => $presetId,
                    'name' => 'Automation Zone A',
                    'description' => 'Primary automation zone with active cycle',
                    'status' => 'RUNNING',
                    'health_score' => 88,
                    'health_status' => 'good',
                    'capabilities' => $fullCapabilities,
                    'hardware_profile' => $fullHardware,
                    'settings' => $baseSettings,
                ]
            ),
            'paused' => Zone::updateOrCreate(
                ['uid' => 'zn-lite-pause-1'],
                [
                    'greenhouse_id' => $greenhouse->id,
                    'preset_id' => $presetId,
                    'name' => 'Automation Zone B',
                    'description' => 'Paused cycle for status validation',
                    'status' => 'PAUSED',
                    'health_score' => 62,
                    'health_status' => 'maintenance',
                    'capabilities' => array_merge($fullCapabilities, ['light_control' => false]),
                    'hardware_profile' => $fullHardware,
                    'settings' => $baseSettings,
                ]
            ),
            'planned' => Zone::updateOrCreate(
                ['uid' => 'zn-lite-plan-1'],
                [
                    'greenhouse_id' => $greenhouse->id,
                    'preset_id' => $presetId,
                    'name' => 'Automation Zone C',
                    'description' => 'Planned cycle for schedule validation',
                    'status' => 'RUNNING',
                    'health_score' => 74,
                    'health_status' => 'healthy',
                    'capabilities' => array_merge($fullCapabilities, ['ph_control' => false, 'ec_control' => false]),
                    'hardware_profile' => array_merge($fullHardware, ['has_ph_sensor' => false, 'has_ec_sensor' => false]),
                    'settings' => $baseSettings,
                ]
            ),
            'empty' => Zone::updateOrCreate(
                ['uid' => 'zn-lite-empty-1'],
                [
                    'greenhouse_id' => $greenhouse->id,
                    'preset_id' => $presetId,
                    'name' => 'Automation Zone D',
                    'description' => 'Zone without active cycle',
                    'status' => 'STOPPED',
                    'health_score' => 30,
                    'health_status' => 'stopped',
                    'capabilities' => ['climate_control' => true],
                    'hardware_profile' => ['has_temperature_sensor' => true, 'has_humidity_sensor' => true],
                    'settings' => $baseSettings,
                ]
            ),
        ];

        return $zones;
    }

    /**
     * @param  array{running: Zone, paused: Zone, planned: Zone, empty: Zone}  $zones
     * @return array{running: DeviceNode, paused: DeviceNode, planned: DeviceNode}
     */
    private function createNodesAndChannels(array $zones): array
    {
        $runningNode = $this->createNodeWithChannels(
            $zones['running'],
            'nd-lite-ctrl-1',
            'automation',
            'Automation Controller',
            'online',
            [
                ['channel' => 'ph_sensor', 'metric' => 'PH', 'unit' => 'pH'],
                ['channel' => 'ec_sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
                ['channel' => 'air_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
                ['channel' => 'air_rh', 'metric' => 'HUMIDITY', 'unit' => '%'],
                ['channel' => 'co2_ppm', 'metric' => 'CO2', 'unit' => 'ppm'],
            ],
            [
                ['channel' => 'main_pump', 'metric' => 'RELAY', 'unit' => 'bool'],
                ['channel' => 'fan', 'metric' => 'RELAY', 'unit' => 'bool'],
                ['channel' => 'heater', 'metric' => 'RELAY', 'unit' => 'bool'],
                ['channel' => 'light', 'metric' => 'RELAY', 'unit' => 'bool'],
                ['channel' => 'mister', 'metric' => 'RELAY', 'unit' => 'bool'],
            ]
        );

        $pausedNode = $this->createNodeWithChannels(
            $zones['paused'],
            'nd-lite-climate-2',
            'climate',
            'Climate Node',
            'offline',
            [
                ['channel' => 'air_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
                ['channel' => 'air_rh', 'metric' => 'HUMIDITY', 'unit' => '%'],
            ],
            []
        );

        $plannedNode = $this->createNodeWithChannels(
            $zones['planned'],
            'nd-lite-sensor-3',
            'sensor',
            'Planned Sensor Node',
            'online',
            [
                ['channel' => 'air_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
                ['channel' => 'air_rh', 'metric' => 'HUMIDITY', 'unit' => '%'],
            ],
            []
        );

        return [
            'running' => $runningNode,
            'paused' => $pausedNode,
            'planned' => $plannedNode,
        ];
    }

    private function createNodeWithChannels(
        Zone $zone,
        string $uid,
        string $type,
        string $name,
        string $status,
        array $sensorChannels,
        array $actuatorChannels
    ): DeviceNode {
        $node = DeviceNode::updateOrCreate(
            ['uid' => $uid],
            [
                'zone_id' => $zone->id,
                'hardware_id' => 'esp32-lite-'.Str::random(6),
                'type' => $type,
                'name' => $name,
                'status' => $status,
                'lifecycle_state' => 'ASSIGNED_TO_ZONE',
                'last_seen_at' => now(),
                'config' => [
                    'sensors' => array_column($sensorChannels, 'channel'),
                    'actuators' => array_column($actuatorChannels, 'channel'),
                ],
            ]
        );

        foreach ($sensorChannels as $channel) {
            NodeChannel::updateOrCreate(
                ['node_id' => $node->id, 'channel' => $channel['channel']],
                [
                    'type' => 'sensor',
                    'metric' => $channel['metric'],
                    'unit' => $channel['unit'],
                    'config' => ['data_type' => 'float'],
                ]
            );
        }

        foreach ($actuatorChannels as $channel) {
            NodeChannel::updateOrCreate(
                ['node_id' => $node->id, 'channel' => $channel['channel']],
                [
                    'type' => 'actuator',
                    'metric' => $channel['metric'],
                    'unit' => $channel['unit'],
                    'config' => ['data_type' => 'boolean'],
                ]
            );
        }

        return $node;
    }

    private function createInfrastructure(Zone $zone, DeviceNode $node): void
    {
        $assets = [
            ['asset_type' => 'PUMP', 'channel' => 'main_pump', 'label' => 'Main Pump', 'required' => true, 'role' => 'main_pump'],
            ['asset_type' => 'FAN', 'channel' => 'fan', 'label' => 'Ventilation Fan', 'required' => true, 'role' => 'fan'],
            ['asset_type' => 'HEATER', 'channel' => 'heater', 'label' => 'Heater', 'required' => true, 'role' => 'heater'],
            ['asset_type' => 'LIGHT', 'channel' => 'light', 'label' => 'Grow Light', 'required' => false, 'role' => 'light'],
            ['asset_type' => 'MISTER', 'channel' => 'mister', 'label' => 'Mister', 'required' => false, 'role' => 'mister'],
        ];

        foreach ($assets as $asset) {
            $infra = InfrastructureInstance::updateOrCreate(
                [
                    'owner_type' => 'zone',
                    'owner_id' => $zone->id,
                    'asset_type' => $asset['asset_type'],
                    'label' => $asset['label'],
                ],
                [
                    'required' => $asset['required'],
                ]
            );

            $channel = NodeChannel::query()
                ->where('node_id', $node->id)
                ->where('channel', $asset['channel'])
                ->first();

            if (! $channel) {
                continue;
            }

            ChannelBinding::updateOrCreate(
                [
                    'infrastructure_instance_id' => $infra->id,
                    'node_channel_id' => $channel->id,
                ],
                [
                    'direction' => $channel->type === 'actuator' ? 'actuator' : 'sensor',
                    'role' => $asset['role'],
                ]
            );
        }
    }

    /**
     * @return array{Plant, RecipeRevision}
     */
    private function createRecipe(): array
    {
        $plant = Plant::updateOrCreate(
            ['slug' => 'lite-lettuce'],
            [
                'name' => 'Lite Lettuce',
                'species' => 'Lactuca sativa',
            ]
        );

        $recipe = Recipe::updateOrCreate(
            ['name' => 'Automation Lite Recipe'],
            [
                'description' => 'Recipe tailored for automation engine preview',
                'metadata' => ['source' => 'lite-seed'],
            ]
        );

        $recipe->plants()->syncWithoutDetaching([
            $plant->id => [
                'season' => 'all_year',
                'site_type' => 'indoor',
                'is_default' => true,
                'metadata' => json_encode(['source' => 'lite-seed'], JSON_UNESCAPED_UNICODE),
            ],
        ]);

        $creatorId = User::query()->where('role', 'admin')->value('id') ?? User::query()->value('id');

        $revision = RecipeRevision::updateOrCreate(
            ['recipe_id' => $recipe->id, 'revision_number' => 1],
            [
                'status' => 'PUBLISHED',
                'description' => 'Lite revision for automation preview',
                'created_by' => $creatorId,
                'published_at' => now(),
            ]
        );

        $germination = GrowStageTemplate::firstOrCreate(
            ['code' => 'GERMINATION'],
            [
                'name' => 'Проращивание',
                'order_index' => 0,
                'default_duration_days' => 3,
                'ui_meta' => ['color' => '#CDDC39', 'icon' => 'sprout'],
            ]
        );

        $vegetation = GrowStageTemplate::firstOrCreate(
            ['code' => 'VEG'],
            [
                'name' => 'Вегетация',
                'order_index' => 1,
                'default_duration_days' => 10,
                'ui_meta' => ['color' => '#2196F3', 'icon' => 'leaf'],
            ]
        );

        RecipeRevisionPhase::updateOrCreate(
            ['recipe_revision_id' => $revision->id, 'phase_index' => 0],
            [
                'stage_template_id' => $germination->id,
                'name' => 'Germination',
                'duration_hours' => 72,
                'ph_target' => 6.0,
                'ph_min' => 5.8,
                'ph_max' => 6.2,
                'ec_target' => 1.0,
                'ec_min' => 0.8,
                'ec_max' => 1.2,
                'irrigation_mode' => 'RECIRC',
                'irrigation_interval_sec' => 900,
                'irrigation_duration_sec' => 8,
                'lighting_photoperiod_hours' => 16,
                'temp_air_target' => 22.0,
                'humidity_target' => 70.0,
                'co2_target' => 800,
            ]
        );

        RecipeRevisionPhase::updateOrCreate(
            ['recipe_revision_id' => $revision->id, 'phase_index' => 1],
            [
                'stage_template_id' => $vegetation->id,
                'name' => 'Growth',
                'duration_hours' => 240,
                'ph_target' => 6.1,
                'ph_min' => 5.7,
                'ph_max' => 6.4,
                'ec_target' => 1.6,
                'ec_min' => 1.3,
                'ec_max' => 1.9,
                'irrigation_mode' => 'RECIRC',
                'irrigation_interval_sec' => 1200,
                'irrigation_duration_sec' => 10,
                'lighting_photoperiod_hours' => 18,
                'temp_air_target' => 24.0,
                'humidity_target' => 65.0,
                'co2_target' => 900,
            ]
        );

        return [$plant, $revision];
    }

    /**
     * @param  array{running: Zone, paused: Zone, planned: Zone, empty: Zone}  $zones
     * @return array{running: GrowCycle, paused: GrowCycle, planned: GrowCycle}
     */
    private function createCycles(array $zones, RecipeRevision $revision, int $plantId): array
    {
        $service = app(GrowCycleService::class);
        $totalHours = (int) RecipeRevisionPhase::query()
            ->where('recipe_revision_id', $revision->id)
            ->sum('duration_hours');

        $running = $this->ensureCycle(
            $service,
            $zones['running'],
            $revision,
            $plantId,
            'lite-running',
            GrowCycleStatus::RUNNING,
            now()->subDays(3)
        );

        $paused = $this->ensureCycle(
            $service,
            $zones['paused'],
            $revision,
            $plantId,
            'lite-paused',
            GrowCycleStatus::PAUSED,
            now()->subDays(5)
        );

        $planned = $this->ensureCycle(
            $service,
            $zones['planned'],
            $revision,
            $plantId,
            'lite-planned',
            GrowCycleStatus::PLANNED,
            now()->addDays(1)
        );

        foreach ([$running, $paused, $planned] as $cycle) {
            if (! $cycle->planting_at || $totalHours <= 0) {
                continue;
            }
            $expectedHarvest = Carbon::parse($cycle->planting_at)->addHours($totalHours);
            $cycle->update(['expected_harvest_at' => $expectedHarvest]);
        }

        return [
            'running' => $running,
            'paused' => $paused,
            'planned' => $planned,
        ];
    }

    private function ensureCycle(
        GrowCycleService $service,
        Zone $zone,
        RecipeRevision $revision,
        int $plantId,
        string $label,
        GrowCycleStatus $status,
        Carbon $plantingAt
    ): GrowCycle {
        $cycle = GrowCycle::query()
            ->where('zone_id', $zone->id)
            ->where('batch_label', $label)
            ->first();

        if (! $cycle) {
            $cycle = $service->createCycle($zone, $revision, $plantId, [
                'start_immediately' => $status !== GrowCycleStatus::PLANNED,
                'planting_at' => $plantingAt,
                'batch_label' => $label,
            ]);
        }

        $updates = [
            'status' => $status,
            'planting_at' => $plantingAt,
            'started_at' => $status === GrowCycleStatus::PLANNED ? null : $plantingAt,
            'phase_started_at' => $status === GrowCycleStatus::PLANNED ? null : $plantingAt,
        ];

        $cycle->update($updates);

        return $cycle->fresh(['currentPhase', 'recipeRevision']);
    }

    /**
     * @param  array{running: Zone, paused: Zone, planned: Zone, empty: Zone}  $zones
     * @param  array{running: DeviceNode, paused: DeviceNode, planned: DeviceNode}  $nodes
     * @param  array{running: GrowCycle, paused: GrowCycle, planned: GrowCycle}  $cycles
     */
    private function seedTelemetry(array $zones, array $nodes, array $cycles): void
    {
        $this->seedTelemetryForNode($zones['running'], $nodes['running'], $cycles['running']);
        $this->seedTelemetryForNode($zones['paused'], $nodes['paused'], $cycles['paused']);
        $this->seedTelemetryForNode($zones['planned'], $nodes['planned'], $cycles['planned']);
    }

    private function seedTelemetryForNode(Zone $zone, DeviceNode $node, GrowCycle $cycle): void
    {
        $channels = NodeChannel::query()
            ->where('node_id', $node->id)
            ->where('type', 'sensor')
            ->get();

        if ($channels->isEmpty()) {
            return;
        }

        $now = now();
        $samplesPerSensor = 12;
        $intervalMinutes = 30;
        $startTime = $now->copy()->subMinutes($intervalMinutes * ($samplesPerSensor - 1));

        foreach ($channels as $channel) {
            $sensorType = $this->sensorTypeFromMetric((string) $channel->metric);
            if (! $sensorType) {
                continue;
            }

            $sensor = Sensor::updateOrCreate(
                [
                    'greenhouse_id' => $zone->greenhouse_id,
                    'zone_id' => $zone->id,
                    'node_id' => $node->id,
                    'scope' => 'inside',
                    'type' => $sensorType,
                    'label' => $this->buildSensorLabel($channel->channel, $sensorType),
                ],
                [
                    'unit' => $channel->unit,
                    'specs' => [
                        'channel' => $channel->channel,
                        'metric' => $channel->metric,
                    ],
                    'is_active' => true,
                    'last_read_at' => $now,
                ]
            );

            $baseValue = $this->baseValueForMetric($sensorType);
            $variation = $this->variationForMetric($sensorType);

            for ($i = 0; $i < $samplesPerSensor; $i++) {
                $ts = $startTime->copy()->addMinutes($i * $intervalMinutes);
                $value = $this->generateValue($baseValue, $variation, $i, $samplesPerSensor);

                TelemetrySample::updateOrCreate(
                    [
                        'sensor_id' => $sensor->id,
                        'ts' => $ts,
                    ],
                    [
                        'zone_id' => $zone->id,
                        'cycle_id' => $cycle->id,
                        'value' => round($value, 2),
                        'quality' => 'GOOD',
                        'metadata' => [
                            'channel' => $channel->channel,
                            'metric' => $channel->metric,
                        ],
                    ]
                );
            }

            TelemetryLast::updateOrCreate(
                ['sensor_id' => $sensor->id],
                [
                    'last_value' => round($baseValue, 2),
                    'last_ts' => $now,
                    'last_quality' => 'GOOD',
                ]
            );
        }
    }

    /**
     * @param  array{running: Zone, paused: Zone, planned: Zone, empty: Zone}  $zones
     * @param  array{running: DeviceNode, paused: DeviceNode, planned: DeviceNode}  $nodes
     * @param  array{running: GrowCycle, paused: GrowCycle, planned: GrowCycle}  $cycles
     */
    private function seedAutomationSignals(array $zones, array $nodes, array $cycles): void
    {
        Alert::updateOrCreate(
            [
                'zone_id' => $zones['running']->id,
                'code' => 'CLIMATE_WARNING',
            ],
            [
                'source' => 'automation',
                'type' => 'CLIMATE',
                'details' => ['message' => 'Humidity deviated from target'],
                'status' => 'ACTIVE',
                'created_at' => now()->subHours(4),
            ]
        );

        ZoneEvent::updateOrCreate(
            [
                'zone_id' => $zones['running']->id,
                'type' => 'AUTOMATION_TICK',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycles['running']->id,
            ],
            [
                'payload_json' => [
                    'message' => 'Automation engine evaluated targets',
                    'cycle_id' => $cycles['running']->id,
                ],
                'server_ts' => now()->timestamp * 1000,
            ]
        );

        $this->seedCycleCommand($zones['running'], $nodes['running'], 'FORCE_PH_CONTROL', 15);
        $this->seedCycleCommand($zones['running'], $nodes['running'], 'FORCE_EC_CONTROL', 20);
        $this->seedCycleCommand($zones['running'], $nodes['running'], 'FORCE_IRRIGATION', 30);
        $this->seedCycleCommand($zones['running'], $nodes['running'], 'FORCE_LIGHTING', 45);
        $this->seedCycleCommand($zones['running'], $nodes['running'], 'FORCE_CLIMATE', 60);
    }

    private function seedCycleCommand(Zone $zone, DeviceNode $node, string $cmd, int $minutesAgo): void
    {
        $ackAt = now()->subMinutes($minutesAgo);

        Command::updateOrCreate(
            [
                'cmd_id' => 'lite-'.$cmd,
            ],
            [
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'channel' => 'automation',
                'cmd' => $cmd,
                'command_type' => 'FORCE',
                'params' => ['source' => 'lite-seed'],
                'status' => Command::STATUS_DONE,
                'sent_at' => $ackAt->copy()->subSeconds(4),
                'ack_at' => $ackAt,
                'result_code' => 0,
                'duration_ms' => 400,
                'created_at' => $ackAt->copy()->subSeconds(6),
            ]
        );
    }

    private function sensorTypeFromMetric(string $metric): ?string
    {
        $metric = strtoupper($metric);

        return match ($metric) {
            'PH' => 'PH',
            'EC' => 'EC',
            'TEMPERATURE' => 'TEMPERATURE',
            'HUMIDITY' => 'HUMIDITY',
            'CO2' => 'CO2',
            default => null,
        };
    }

    private function baseValueForMetric(string $metric): float
    {
        return match (strtoupper($metric)) {
            'PH' => 6.0,
            'EC' => 1.4,
            'TEMPERATURE' => 22.5,
            'HUMIDITY' => 60.0,
            'CO2' => 850.0,
            default => 0.0,
        };
    }

    private function variationForMetric(string $metric): float
    {
        return match (strtoupper($metric)) {
            'PH' => 0.15,
            'EC' => 0.25,
            'TEMPERATURE' => 2.0,
            'HUMIDITY' => 8.0,
            'CO2' => 80.0,
            default => 1.0,
        };
    }

    private function generateValue(float $base, float $variation, int $index, int $total): float
    {
        if ($total <= 1) {
            return $base;
        }

        $t = $index / ($total - 1);
        $trend = sin($t * 2 * M_PI) * ($variation * 0.4);
        $noise = cos($t * 4 * M_PI) * ($variation * 0.2);

        return $base + $trend + $noise;
    }

    private function buildSensorLabel(?string $channel, string $metric): string
    {
        $suffix = $channel ? strtoupper($channel) : strtoupper($metric);

        return "Sensor {$suffix}";
    }
}
