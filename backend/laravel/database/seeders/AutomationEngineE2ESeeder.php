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
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\GrowCycleService;
use App\Services\ZoneLogicProfileCatalog;
use App\Services\ZoneLogicProfileService;
use App\Support\Automation\ZonePidDefaults;
use Carbon\Carbon;
use Database\Seeders\Support\CanonicalRecipePhaseSupport;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;
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
        $this->grantFixtureAccess($greenhouse, $zone);

        // 3. Создаем канонический набор test-node симуляторов, чтобы telemetry/heartbeat
        // не создавали startup drift до первого E2E сценария.
        $seededNodes = [
            [
                'uid' => 'nd-ph-esp32una',
                'hardware_id' => 'esp32-test-001',
                'type' => 'ph',
                'name' => 'E2E Test PH Node',
                'sensors' => [
                    ['channel' => 'ph_sensor', 'metric' => 'PH', 'unit' => 'pH'],
                    ['channel' => 'ec_sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
                    ['channel' => 'solution_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
                    ['channel' => 'air_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
                    ['channel' => 'air_rh', 'metric' => 'HUMIDITY', 'unit' => '%'],
                ],
                'actuators' => [
                    ['channel' => 'main_pump', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'main_pump'],
                    ['channel' => 'drain_pump', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'drain'],
                    ['channel' => 'fan', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'fan'],
                    ['channel' => 'heater', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'heater'],
                    ['channel' => 'light', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'light'],
                    ['channel' => 'mister', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'mist'],
                ],
            ],
            [
                'uid' => 'nd-test-irrig-1',
                'hardware_id' => 'nd-test-irrig-1',
                'type' => 'irrig',
                'name' => 'E2E Test Irrigation Node',
                'sensors' => [
                    ['channel' => 'level_clean_min', 'metric' => 'WATER_LEVEL_SWITCH', 'unit' => 'bool'],
                    ['channel' => 'level_clean_max', 'metric' => 'WATER_LEVEL_SWITCH', 'unit' => 'bool'],
                    ['channel' => 'level_solution_min', 'metric' => 'WATER_LEVEL_SWITCH', 'unit' => 'bool'],
                    ['channel' => 'level_solution_max', 'metric' => 'WATER_LEVEL_SWITCH', 'unit' => 'bool'],
                ],
                'actuators' => [
                    ['channel' => 'pump_main', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'main_pump'],
                    ['channel' => 'valve_clean_fill', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'valve_clean_fill'],
                    ['channel' => 'valve_clean_supply', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'valve_clean_supply'],
                    ['channel' => 'valve_solution_fill', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'valve_solution_fill'],
                    ['channel' => 'valve_solution_supply', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'valve_solution_supply'],
                    ['channel' => 'valve_irrigation', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'valve_irrigation'],
                ],
            ],
            [
                'uid' => 'nd-test-ph-1',
                'hardware_id' => 'nd-test-ph-1',
                'type' => 'ph',
                'name' => 'E2E Test pH Dosing Node',
                'sensors' => [
                    ['channel' => 'ph_sensor', 'metric' => 'PH', 'unit' => 'pH'],
                ],
                'actuators' => [
                    ['channel' => 'pump_acid', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'pump_acid'],
                    ['channel' => 'pump_base', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'pump_base'],
                    ['channel' => 'system', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'system'],
                ],
            ],
            [
                'uid' => 'nd-test-ec-1',
                'hardware_id' => 'nd-test-ec-1',
                'type' => 'ec',
                'name' => 'E2E Test EC Dosing Node',
                'sensors' => [
                    ['channel' => 'ec_sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
                ],
                'actuators' => [
                    ['channel' => 'pump_a', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'pump_a'],
                    ['channel' => 'pump_b', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'pump_b'],
                    ['channel' => 'pump_c', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'pump_c'],
                    ['channel' => 'pump_d', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'pump_d'],
                    ['channel' => 'system', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'system'],
                ],
            ],
            [
                'uid' => 'nd-test-climate-1',
                'hardware_id' => 'nd-test-climate-1',
                'type' => 'climate',
                'name' => 'E2E Test Climate Node',
                'sensors' => [
                    ['channel' => 'air_temp_c', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
                    ['channel' => 'air_rh', 'metric' => 'HUMIDITY', 'unit' => '%'],
                ],
                'actuators' => [
                    ['channel' => 'fan_air', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'fan_air'],
                    ['channel' => 'fan', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'fan'],
                    ['channel' => 'heater', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'heater'],
                ],
            ],
            [
                'uid' => 'nd-test-light-1',
                'hardware_id' => 'nd-test-light-1',
                'type' => 'light',
                'name' => 'E2E Test Light Node',
                'sensors' => [
                    ['channel' => 'light_level', 'metric' => 'LIGHT_INTENSITY', 'unit' => 'lux'],
                ],
                'actuators' => [
                    ['channel' => 'white_light', 'metric' => 'RELAY', 'unit' => 'bool', 'zone_role' => 'white_light'],
                ],
            ],
        ];

        $seedNodeChannels = static function (DeviceNode $seededNode, array $sensorChannels, array $actuatorChannels): void {
            NodeChannel::withoutEvents(function () use ($actuatorChannels, $seededNode, $sensorChannels): void {
                foreach ($sensorChannels as $channelData) {
                    NodeChannel::updateOrCreate(
                        [
                            'node_id' => $seededNode->id,
                            'channel' => $channelData['channel'],
                        ],
                        [
                            'type' => 'sensor',
                            'metric' => $channelData['metric'],
                            'unit' => $channelData['unit'],
                            'config' => ['data_type' => 'float'],
                            'is_active' => true,
                        ]
                    );
                }

                foreach ($actuatorChannels as $channelData) {
                    NodeChannel::updateOrCreate(
                        [
                            'node_id' => $seededNode->id,
                            'channel' => $channelData['channel'],
                        ],
                        [
                            'type' => 'actuator',
                            'metric' => $channelData['metric'],
                            'unit' => $channelData['unit'],
                            'config' => [
                                'data_type' => 'boolean',
                                'zone_role' => $channelData['zone_role'] ?? $channelData['channel'],
                            ],
                            'is_active' => true,
                        ]
                    );
                }
            });
        };

        $primaryNode = null;
        foreach ($seededNodes as $nodeData) {
            $seededNode = DeviceNode::updateOrCreate(
                ['uid' => $nodeData['uid']],
                [
                    'zone_id' => $zone->id,
                    'pending_zone_id' => null,
                    'hardware_id' => $nodeData['hardware_id'],
                    'type' => $nodeData['type'],
                    'name' => $nodeData['name'],
                    'status' => 'online',
                    'lifecycle_state' => 'ASSIGNED_TO_ZONE',
                    'last_seen_at' => Carbon::now(),
                    'last_heartbeat_at' => Carbon::now(),
                    'config' => [
                        'sensors' => array_column($nodeData['sensors'], 'channel'),
                        'actuators' => array_column($nodeData['actuators'], 'channel'),
                    ],
                ]
            );

            $seedNodeChannels($seededNode, $nodeData['sensors'], $nodeData['actuators']);
            $this->command->info("✓ Node created: {$seededNode->id} (uid: {$seededNode->uid})");

            if ($nodeData['uid'] === 'nd-ph-esp32una') {
                $primaryNode = $seededNode;
            }
        }

        /** @var DeviceNode $node */
        $node = $primaryNode ?? DeviceNode::query()->where('uid', 'nd-ph-esp32una')->firstOrFail();
        $this->command->info('✓ Channels created for canonical E2E nodes');

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
        $adminId = $creatorId ? (int) $creatorId : null;

        $documents = app(AutomationConfigDocumentService::class);
        $documents->ensureSystemDefaults();
        $documents->ensureZoneDefaults((int) $zone->id);
        app(ZoneLogicProfileService::class)->upsertProfile(
            zone: $zone,
            mode: ZoneLogicProfileCatalog::MODE_WORKING,
            subsystems: $this->defaultAutomationSubsystems(),
            activate: true,
            userId: $adminId,
        );
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            ZonePidDefaults::forType('ph'),
            $adminId,
            'automation_engine_e2e_seed'
        );
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            ZonePidDefaults::forType('ec'),
            $adminId,
            'automation_engine_e2e_seed'
        );
        $this->cleanupFixtureRuntimeState($zone);

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
                'irrigation_mode' => 'SUBSTRATE',
                'lighting_start_time' => '06:00:00',
                'extensions' => CanonicalRecipePhaseSupport::mergeExtensions(
                    null,
                    'SUBSTRATE',
                    CanonicalRecipePhaseSupport::buildDayNight(22.0, 22.0, 70.0, 70.0, 6.0, 6.0, 1.0, 1.0, '06:00:00', null)
                ),
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
                'irrigation_mode' => 'SUBSTRATE',
                'lighting_start_time' => '06:00:00',
                'extensions' => CanonicalRecipePhaseSupport::mergeExtensions(
                    null,
                    'SUBSTRATE',
                    CanonicalRecipePhaseSupport::buildDayNight(24.0, 24.0, 65.0, 65.0, 6.0, 6.0, 1.5, 1.5, '06:00:00', null)
                ),
            ]
        );

        $this->command->info('✓ Recipe revision and phases created');
        $this->cleanupFixtureAlerts($zone);

        // 8. Создаем активный grow-cycle (если еще нет)
        $existingCycle = GrowCycle::where('zone_id', $zone->id)
            ->whereIn('status', ['PLANNED', 'RUNNING', 'PAUSED'])
            ->orderByDesc('created_at')
            ->first();

        $plantingAt = Carbon::now()->subDays(5)->setMicroseconds(0);

        if ($existingCycle) {
            $growCycle = $existingCycle;
            app(GrowCycleService::class)->syncCycleConfigDocuments(
                $growCycle->fresh(),
                ['planting_at' => $plantingAt->toIso8601String()],
                $adminId
            );

            if ($growCycle->status === 'PLANNED') {
                $growCycle = app(GrowCycleService::class)->startCycle($growCycle->fresh(), $plantingAt->copy());
            } elseif ($growCycle->status === 'PAUSED') {
                $growCycle = app(GrowCycleService::class)->resume($growCycle->fresh(), $adminId ?? 0);
            }

            $this->command->info("✓ Grow cycle already exists: {$growCycle->id}");
        } else {
            $service = app(GrowCycleService::class);
            $growCycle = $service->createCycle($zone, $revision, $plant->id, [
                'start_immediately' => false,
                'planting_at' => $plantingAt->toIso8601String(),
            ], $adminId);
            $service->syncCycleConfigDocuments(
                $growCycle->fresh(),
                ['planting_at' => $plantingAt->toIso8601String()],
                $adminId
            );
            $growCycle = $service->startCycle($growCycle->fresh(), $plantingAt->copy());

            $this->command->info("✓ Grow cycle created: {$growCycle->id}");
        }

        $this->command->info('=== E2E Automation Engine seed completed ===');
        $this->command->info("Zone ID: {$zone->id}");
        $this->command->info("Zone UID: {$zone->uid}");
        $this->command->info("Node UID: {$node->uid}");
        $this->command->info("Recipe ID: {$recipe->id}");
        $this->command->info("Grow Cycle ID: {$growCycle->id}");
    }

    private function grantFixtureAccess(Greenhouse $greenhouse, Zone $zone): void
    {
        $users = User::query()
            ->where('email', 'e2e@test.local')
            ->orWhere('role', 'agronomist')
            ->get();

        foreach ($users as $user) {
            if ($user->isAdmin()) {
                continue;
            }

            $user->greenhouses()->syncWithoutDetaching([(int) $greenhouse->id]);
            $user->zones()->syncWithoutDetaching([(int) $zone->id]);
        }
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

    private function cleanupFixtureAlerts(Zone $zone): void
    {
        DB::table('alerts')
            ->where(function ($query) use ($zone): void {
                $query->where('zone_id', (int) $zone->id)
                    ->orWhereRaw("COALESCE(details->>'gh_uid', '') = 'gh-test-1'")
                    ->orWhereRaw("COALESCE(details->>'zone_uid', '') = 'zn-test-1'");
            })
            ->whereIn('code', [
                'biz_ae3_task_failed',
                'infra_telemetry_zone_not_found',
                'infra_telemetry_node_not_found',
                'infra_telemetry_sample_dropped_node_not_found',
                'infra_telemetry_sample_dropped_zone_not_found',
                'biz_zone_pid_config_missing',
            ])
            ->delete();
    }

    private function cleanupFixtureRuntimeState(Zone $zone): void
    {
        $zoneId = (int) $zone->id;

        DB::table('ae_commands')
            ->whereIn('task_id', function ($query) use ($zoneId): void {
                $query->select('id')
                    ->from('ae_tasks')
                    ->where('zone_id', $zoneId);
            })
            ->delete();

        DB::table('ae_tasks')
            ->where('zone_id', $zoneId)
            ->delete();

        DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->delete();

        DB::table('ae_zone_leases')
            ->where('zone_id', $zoneId)
            ->delete();

        DB::table('zone_workflow_state')
            ->where('zone_id', $zoneId)
            ->delete();
    }
}
