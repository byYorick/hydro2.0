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
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Str;

class LiteAutomationSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Lite Automation Engine dataset ===');

        $this->call(AdminUserSeeder::class);
        $this->call(PresetSeeder::class);

        $greenhouses = $this->createGreenhouses();
        $zones = $this->createZones($greenhouses);
        $zoneNodes = $this->createNodesAndChannels($zones);
        $this->cleanupStaleLiteNodes($zoneNodes);

        $this->createInfrastructure($zones, $zoneNodes);

        [$plant, $revision] = $this->createRecipe();
        $cycles = $this->createCycles($zones, $revision, $plant->id);

        $this->seedTelemetry($zones, $zoneNodes, $cycles);
        $this->seedAutomationSignals($zones, $zoneNodes, $cycles);

        $this->command->info('=== Lite Automation Engine seeding complete ===');
    }

    /**
     * @return array{first: Greenhouse, second: Greenhouse}
     */
    private function createGreenhouses(): array
    {
        $first = Greenhouse::updateOrCreate(
            ['uid' => 'gh-1'],
            [
                'name' => 'Automation Lite Greenhouse A',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'coordinates' => ['lat' => 55.7558, 'lon' => 37.6173],
                'description' => 'Lite dataset greenhouse A',
                'provisioning_token' => 'gh_lite_a_'.Str::random(24),
            ]
        );

        $second = Greenhouse::updateOrCreate(
            ['uid' => 'gh-lite-automation-2'],
            [
                'name' => 'Automation Lite Greenhouse B',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'coordinates' => ['lat' => 59.9343, 'lon' => 30.3351],
                'description' => 'Lite dataset greenhouse B',
                'provisioning_token' => 'gh_lite_b_'.Str::random(24),
            ]
        );

        foreach ([$first, $second] as $greenhouse) {
            if (! $greenhouse->provisioning_token) {
                $greenhouse->provisioning_token = 'gh_lite_'.Str::random(24);
                $greenhouse->save();
            }
        }

        return [
            'first' => $first,
            'second' => $second,
        ];
    }

    /**
     * @param  array{first: Greenhouse, second: Greenhouse}  $greenhouses
     * @return array{running: Zone, paused: Zone, planned: Zone, empty: Zone}
     */
    private function createZones(array $greenhouses): array
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

        return [
            'running' => Zone::updateOrCreate(
                ['uid' => 'zn-zona-a'],
                [
                    'greenhouse_id' => $greenhouses['first']->id,
                    'preset_id' => $presetId,
                    'name' => 'Automation Zone A1',
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
                    'greenhouse_id' => $greenhouses['first']->id,
                    'preset_id' => $presetId,
                    'name' => 'Automation Zone A2',
                    'description' => 'Paused cycle for status validation',
                    'status' => 'PAUSED',
                    'health_score' => 67,
                    'health_status' => 'maintenance',
                    'capabilities' => $fullCapabilities,
                    'hardware_profile' => $fullHardware,
                    'settings' => $baseSettings,
                ]
            ),
            'planned' => Zone::updateOrCreate(
                ['uid' => 'zn-lite-plan-1'],
                [
                    'greenhouse_id' => $greenhouses['second']->id,
                    'preset_id' => $presetId,
                    'name' => 'Automation Zone B1',
                    'description' => 'Planned cycle for schedule validation',
                    'status' => 'RUNNING',
                    'health_score' => 74,
                    'health_status' => 'healthy',
                    'capabilities' => $fullCapabilities,
                    'hardware_profile' => $fullHardware,
                    'settings' => $baseSettings,
                ]
            ),
            'empty' => Zone::updateOrCreate(
                ['uid' => 'zn-lite-empty-1'],
                [
                    'greenhouse_id' => $greenhouses['second']->id,
                    'preset_id' => $presetId,
                    'name' => 'Automation Zone B2',
                    'description' => 'Zone without active cycle',
                    'status' => 'STOPPED',
                    'health_score' => 42,
                    'health_status' => 'stopped',
                    'capabilities' => $fullCapabilities,
                    'hardware_profile' => $fullHardware,
                    'settings' => $baseSettings,
                ]
            ),
        ];
    }

    /**
     * @param  array{running: Zone, paused: Zone, planned: Zone, empty: Zone}  $zones
     * @return array<string, array<string, DeviceNode>>
     */
    private function createNodesAndChannels(array $zones): array
    {
        $templates = $this->nodeTemplates();
        $zoneNodes = [];

        foreach ($zones as $zoneKey => $zone) {
            $zoneNodes[$zoneKey] = [];

            foreach ($templates as $role => $template) {
                $uid = $this->nodeUidForZoneRole($zoneKey, $role);

                $nodeStatus = $zoneKey === 'empty' && in_array($role, ['irrigation', 'ph', 'ec'], true)
                    ? 'offline'
                    : 'online';

                $zoneNodes[$zoneKey][$role] = $this->createNodeWithChannels(
                    $zone,
                    $uid,
                    $template['type'],
                    $template['name'],
                    $nodeStatus,
                    $template['sensor_channels'],
                    $template['actuator_channels']
                );
            }
        }

        return $zoneNodes;
    }

    /**
     * @return array<string, array{type: string, name: string, sensor_channels: array<int, array{channel: string, metric: string, unit: string}>, actuator_channels: array<int, array{channel: string, metric: string, unit: string, data_type?: string}>}>
     */
    private function nodeTemplates(): array
    {
        return [
            'climate' => [
                'type' => 'climate',
                'name' => 'Climate Node',
                'sensor_channels' => [
                    ['channel' => 'air_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
                    ['channel' => 'air_rh', 'metric' => 'HUMIDITY', 'unit' => '%'],
                ],
                'actuator_channels' => [
                    ['channel' => 'fan_air', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                ],
            ],
            'irrigation' => [
                'type' => 'irrig',
                'name' => 'Irrigation Node',
                'sensor_channels' => [
                    ['channel' => 'flow_present', 'metric' => 'FLOW_RATE', 'unit' => 'L/min'],
                    ['channel' => 'pump_bus_current', 'metric' => 'PUMP_CURRENT', 'unit' => 'mA'],
                ],
                'actuator_channels' => [
                    ['channel' => 'pump_irrigation', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                ],
            ],
            'ph' => [
                'type' => 'ph',
                'name' => 'pH Node',
                'sensor_channels' => [
                    ['channel' => 'ph_sensor', 'metric' => 'PH', 'unit' => 'pH'],
                ],
                'actuator_channels' => [
                    ['channel' => 'pump_acid', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                    ['channel' => 'pump_base', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                ],
            ],
            'ec' => [
                'type' => 'ec',
                'name' => 'EC Node',
                'sensor_channels' => [
                    ['channel' => 'ec_sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
                ],
                'actuator_channels' => [
                    ['channel' => 'pump_a', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                    ['channel' => 'pump_b', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                    ['channel' => 'pump_c', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                    ['channel' => 'pump_d', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                ],
            ],
            'lighting' => [
                'type' => 'light',
                'name' => 'Lighting Node',
                'sensor_channels' => [
                    ['channel' => 'light_level', 'metric' => 'LIGHT_INTENSITY', 'unit' => 'lux'],
                ],
                'actuator_channels' => [
                    ['channel' => 'white_light', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                ],
            ],
            'water' => [
                'type' => 'water_sensor',
                'name' => 'Water Tanks Node',
                'sensor_channels' => [
                    ['channel' => 'water_level', 'metric' => 'WATER_LEVEL', 'unit' => '%'],
                ],
                'actuator_channels' => [
                    ['channel' => 'pump_in', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                    ['channel' => 'drain_main', 'metric' => 'RELAY', 'unit' => 'bool', 'data_type' => 'boolean'],
                ],
            ],
        ];
    }

    private function nodeUidForZoneRole(string $zoneKey, string $role): string
    {
        if ($zoneKey === 'paused' && $role === 'climate') {
            return 'nd-lite-climate-2';
        }

        if ($zoneKey === 'planned' && $role === 'climate') {
            return 'nd-lite-sensor-3';
        }

        $suffixMap = [
            'running' => 'run',
            'paused' => 'pause',
            'planned' => 'plan',
            'empty' => 'empty',
        ];

        return sprintf('nd-lite-%s-%s', $suffixMap[$zoneKey] ?? $zoneKey, $role);
    }

    /**
     * @param  array<string, array<string, DeviceNode>>  $zoneNodes
     */
    private function cleanupStaleLiteNodes(array $zoneNodes): void
    {
        $expectedUids = [];
        foreach ($zoneNodes as $nodes) {
            foreach ($nodes as $node) {
                $expectedUids[] = $node->uid;
            }
        }

        DeviceNode::query()
            ->where('uid', 'like', 'nd-lite-%')
            ->whereNotIn('uid', $expectedUids)
            ->delete();
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
        $hardwareId = $this->hardwareIdForNodeUid($uid);

        $node = DeviceNode::updateOrCreate(
            ['uid' => $uid],
            [
                'zone_id' => $zone->id,
                'hardware_id' => $hardwareId,
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

        $allChannels = [];

        foreach ($sensorChannels as $channel) {
            $allChannels[] = $channel['channel'];

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
            $allChannels[] = $channel['channel'];

            NodeChannel::updateOrCreate(
                ['node_id' => $node->id, 'channel' => $channel['channel']],
                [
                    'type' => 'actuator',
                    'metric' => $channel['metric'],
                    'unit' => $channel['unit'],
                    'config' => ['data_type' => $channel['data_type'] ?? 'boolean'],
                ]
            );
        }

        NodeChannel::query()
            ->where('node_id', $node->id)
            ->whereNotIn('channel', $allChannels)
            ->delete();

        return $node;
    }

    private function hardwareIdForNodeUid(string $uid): string
    {
        return 'esp32-lite-'.substr(md5($uid), 0, 6);
    }

    /**
     * @param  array{running: Zone, paused: Zone, planned: Zone, empty: Zone}  $zones
     * @param  array<string, array<string, DeviceNode>>  $zoneNodes
     */
    private function createInfrastructure(array $zones, array $zoneNodes): void
    {
        if (! Schema::hasTable('infrastructure_instances') || ! Schema::hasTable('channel_bindings')) {
            $this->command->warn('Infrastructure tables are missing, skipping channel bindings in LiteAutomationSeeder');

            return;
        }

        foreach ($zones as $zoneKey => $zone) {
            $assetMap = [
                ['asset_type' => 'PUMP', 'label' => 'Main Pump', 'node_role' => 'irrigation', 'channel' => 'pump_irrigation', 'role' => 'main_pump', 'required' => true],
                ['asset_type' => 'DRAIN', 'label' => 'Drain', 'node_role' => 'water', 'channel' => 'drain_main', 'role' => 'drain', 'required' => true],
                ['asset_type' => 'PUMP', 'label' => 'pH Acid Pump', 'node_role' => 'ph', 'channel' => 'pump_acid', 'role' => 'ph_acid_pump', 'required' => true],
                ['asset_type' => 'PUMP', 'label' => 'pH Base Pump', 'node_role' => 'ph', 'channel' => 'pump_base', 'role' => 'ph_base_pump', 'required' => true],
                ['asset_type' => 'PUMP', 'label' => 'EC NPK Pump', 'node_role' => 'ec', 'channel' => 'pump_a', 'role' => 'ec_npk_pump', 'required' => true],
                ['asset_type' => 'PUMP', 'label' => 'EC Calcium Pump', 'node_role' => 'ec', 'channel' => 'pump_b', 'role' => 'ec_calcium_pump', 'required' => true],
                ['asset_type' => 'PUMP', 'label' => 'EC Magnesium Pump', 'node_role' => 'ec', 'channel' => 'pump_c', 'role' => 'ec_magnesium_pump', 'required' => true],
                ['asset_type' => 'PUMP', 'label' => 'EC Micro Pump', 'node_role' => 'ec', 'channel' => 'pump_d', 'role' => 'ec_micro_pump', 'required' => true],
                ['asset_type' => 'FAN', 'label' => 'Ventilation Fan', 'node_role' => 'climate', 'channel' => 'fan_air', 'role' => 'fan', 'required' => false],
                ['asset_type' => 'LIGHT', 'label' => 'Grow Light', 'node_role' => 'lighting', 'channel' => 'white_light', 'role' => 'light', 'required' => false],
            ];

            foreach ($assetMap as $asset) {
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

                $node = $zoneNodes[$zoneKey][$asset['node_role']] ?? null;
                if (! $node) {
                    continue;
                }

                $channel = NodeChannel::query()
                    ->where('node_id', $node->id)
                    ->where('channel', $asset['channel'])
                    ->first();

                if (! $channel) {
                    continue;
                }

                ChannelBinding::updateOrCreate(
                    [
                        'node_channel_id' => $channel->id,
                    ],
                    [
                        'infrastructure_instance_id' => $infra->id,
                        'direction' => $channel->type === 'actuator' ? 'actuator' : 'sensor',
                        'role' => $asset['role'],
                    ]
                );
            }
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
                'default_duration_days' => 12,
                'ui_meta' => ['color' => '#2196F3', 'icon' => 'leaf'],
            ]
        );

        RecipeRevisionPhase::updateOrCreate(
            ['recipe_revision_id' => $revision->id, 'phase_index' => 0],
            [
                'stage_template_id' => $germination->id,
                'name' => 'Germination (Day/Night)',
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
                'lighting_start_time' => '06:00:00',
                'temp_air_target' => 22.0,
                'humidity_target' => 70.0,
                'co2_target' => 800,
                'extensions' => [
                    'day_target' => ['temp_air' => 22.0, 'humidity' => 68],
                    'night_target' => ['temp_air' => 20.0, 'humidity' => 72],
                ],
            ]
        );

        RecipeRevisionPhase::updateOrCreate(
            ['recipe_revision_id' => $revision->id, 'phase_index' => 1],
            [
                'stage_template_id' => $vegetation->id,
                'name' => 'Vegetation (Day/Night)',
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
                'lighting_start_time' => '05:00:00',
                'temp_air_target' => 24.0,
                'humidity_target' => 65.0,
                'co2_target' => 900,
                'extensions' => [
                    'day_target' => ['temp_air' => 24.0, 'humidity' => 63],
                    'night_target' => ['temp_air' => 21.0, 'humidity' => 68],
                ],
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
            now()->addDay()
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
            // Для идемпотентности сидера переиспользуем уже существующий активный цикл зоны.
            $cycle = GrowCycle::query()
                ->where('zone_id', $zone->id)
                ->whereIn('status', [
                    GrowCycleStatus::PLANNED,
                    GrowCycleStatus::RUNNING,
                    GrowCycleStatus::PAUSED,
                ])
                ->orderByDesc('id')
                ->first();
        }

        if (! $cycle) {
            $cycle = $service->createCycle($zone, $revision, $plantId, [
                'start_immediately' => $status !== GrowCycleStatus::PLANNED,
                'planting_at' => $plantingAt,
                'batch_label' => $label,
            ]);
        }

        $cycle->update([
            'recipe_revision_id' => $revision->id,
            'plant_id' => $plantId,
            'batch_label' => $label,
            'status' => $status,
            'planting_at' => $plantingAt,
            'started_at' => $status === GrowCycleStatus::PLANNED ? null : $plantingAt,
            'phase_started_at' => $status === GrowCycleStatus::PLANNED ? null : $plantingAt,
        ]);

        return $cycle->fresh(['currentPhase', 'recipeRevision']);
    }

    /**
     * @param  array{running: Zone, paused: Zone, planned: Zone, empty: Zone}  $zones
     * @param  array<string, array<string, DeviceNode>>  $zoneNodes
     * @param  array{running: GrowCycle, paused: GrowCycle, planned: GrowCycle}  $cycles
     */
    private function seedTelemetry(array $zones, array $zoneNodes, array $cycles): void
    {
        foreach ($zones as $zoneKey => $zone) {
            $cycle = $cycles[$zoneKey] ?? null;
            foreach ($zoneNodes[$zoneKey] as $node) {
                $this->seedTelemetryForNode($zone, $node, $cycle);
            }
        }
    }

    private function seedTelemetryForNode(Zone $zone, DeviceNode $node, ?GrowCycle $cycle): void
    {
        $channels = NodeChannel::query()
            ->where('node_id', $node->id)
            ->where('type', 'sensor')
            ->get();

        if ($channels->isEmpty()) {
            return;
        }

        $now = $this->seedBaseTime()->copy()->addMinutes($this->timeOffsetForNode($node));
        $samplesPerSensor = 4;
        $intervalMinutes = 20;
        $startTime = $now->copy()->subMinutes($intervalMinutes * ($samplesPerSensor - 1));

        foreach ($channels as $channel) {
            $sensorType = $this->sensorTypeFromMetric((string) $channel->metric);
            if (! $sensorType) {
                continue;
            }

            $sensor = Sensor::updateOrCreate(
                [
                    'zone_id' => $zone->id,
                    'node_id' => $node->id,
                    'scope' => 'inside',
                    'type' => $sensorType,
                    'label' => $this->buildSensorLabel($channel->channel, $sensorType),
                ],
                [
                    'greenhouse_id' => $zone->greenhouse_id,
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
                        'cycle_id' => $cycle?->id,
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
     * @param  array<string, array<string, DeviceNode>>  $zoneNodes
     * @param  array{running: GrowCycle, paused: GrowCycle, planned: GrowCycle}  $cycles
     */
    private function seedAutomationSignals(array $zones, array $zoneNodes, array $cycles): void
    {
        $baseTime = $this->seedBaseTime();

        Alert::updateOrCreate(
            [
                'zone_id' => $zones['running']->id,
                'code' => 'CLIMATE_WARNING',
            ],
            [
                'source' => 'automation',
                'type' => 'CLIMATE',
                'details' => ['message' => 'Влажность отклонилась от целевого диапазона'],
                'status' => 'ACTIVE',
                'created_at' => $baseTime->copy()->subHour(),
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
                'server_ts' => $baseTime->timestamp * 1000,
            ]
        );

        $this->seedCycleCommand($zones['running'], $zoneNodes['running']['ph'], 'FORCE_PH_CONTROL', $baseTime->copy()->subMinutes(10));
        $this->seedCycleCommand($zones['running'], $zoneNodes['running']['irrigation'], 'FORCE_IRRIGATION', $baseTime->copy()->subMinutes(6));
    }

    private function seedCycleCommand(Zone $zone, DeviceNode $node, string $cmd, Carbon $ackAt): void
    {
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
                'duration_ms' => 360,
                'created_at' => $ackAt->copy()->subSeconds(6),
            ]
        );
    }

    private function sensorTypeFromMetric(string $metric): ?string
    {
        return match (strtoupper($metric)) {
            'PH' => 'PH',
            'EC' => 'EC',
            'TEMPERATURE' => 'TEMPERATURE',
            'HUMIDITY' => 'HUMIDITY',
            'CO2' => 'CO2',
            'WATER_LEVEL' => 'WATER_LEVEL',
            'PRESSURE' => 'PRESSURE',
            'FLOW_RATE' => 'FLOW_RATE',
            'PUMP_CURRENT' => 'PUMP_CURRENT',
            'LIGHT_INTENSITY' => 'LIGHT_INTENSITY',
            default => null,
        };
    }

    private function baseValueForMetric(string $metric): float
    {
        return match (strtoupper($metric)) {
            'PH' => 6.0,
            'EC' => 1.4,
            'TEMPERATURE' => 22.4,
            'HUMIDITY' => 62.0,
            'CO2' => 840.0,
            'WATER_LEVEL' => 73.0,
            'PRESSURE' => 1.6,
            'FLOW_RATE' => 1.2,
            'PUMP_CURRENT' => 180.0,
            'LIGHT_INTENSITY' => 18500.0,
            default => 0.0,
        };
    }

    private function variationForMetric(string $metric): float
    {
        return match (strtoupper($metric)) {
            'PH' => 0.12,
            'EC' => 0.2,
            'TEMPERATURE' => 1.8,
            'HUMIDITY' => 7.0,
            'CO2' => 70.0,
            'WATER_LEVEL' => 4.0,
            'PRESSURE' => 0.35,
            'FLOW_RATE' => 0.3,
            'PUMP_CURRENT' => 25.0,
            'LIGHT_INTENSITY' => 1500.0,
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

    private function seedBaseTime(): Carbon
    {
        return Carbon::parse('2026-01-15 12:00:00', 'UTC');
    }

    private function timeOffsetForNode(DeviceNode $node): int
    {
        return abs(crc32($node->uid)) % 60;
    }
}
