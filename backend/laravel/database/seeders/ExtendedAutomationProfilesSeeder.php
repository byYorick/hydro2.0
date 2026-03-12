<?php

namespace Database\Seeders;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneAutomationLogicProfile;
use App\Models\ZoneEvent;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Schema;

/**
 * Создаёт zone_automation_logic_profiles и начальные IRR_STATE_SNAPSHOT события
 * для всех зон, у которых ещё нет профиля.
 */
class ExtendedAutomationProfilesSeeder extends Seeder
{
    public function run(): void
    {
        if (! Schema::hasTable('zone_automation_logic_profiles')) {
            $this->command->warn('zone_automation_logic_profiles table not found, skipping');

            return;
        }

        $adminId = User::query()->where('role', 'admin')->value('id') ?? User::query()->value('id');
        $commandPlans = $this->defaultCommandPlans();
        $subsystems = [
            'diagnostics' => [
                'enabled' => true,
                'execution' => [
                    'workflow' => 'cycle_start',
                    'topology' => 'two_tank_drip_substrate_trays',
                ],
            ],
        ];

        $zones = Zone::all(['id']);
        $created = 0;

        foreach ($zones as $zone) {
            $exists = ZoneAutomationLogicProfile::query()
                ->where('zone_id', $zone->id)
                ->where('is_active', true)
                ->exists();

            if ($exists) {
                continue;
            }

            ZoneAutomationLogicProfile::updateOrCreate(
                ['zone_id' => $zone->id, 'mode' => ZoneAutomationLogicProfile::MODE_WORKING],
                [
                    'is_active' => true,
                    'subsystems' => $subsystems,
                    'command_plans' => $commandPlans,
                    'created_by' => $adminId,
                    'updated_by' => $adminId,
                ]
            );

            $created++;
        }

        $this->command->info("Automation profiles created for {$created} zones (skipped existing)");

        $this->seedIrrStateEvents($zones);
    }

    /**
     * @param  \Illuminate\Database\Eloquent\Collection<int, Zone>  $zones
     */
    private function seedIrrStateEvents($zones): void
    {
        if (! Schema::hasTable('zone_events')) {
            return;
        }

        $now = now();
        $seeded = 0;

        foreach ($zones as $zone) {
            $exists = ZoneEvent::query()
                ->where('zone_id', $zone->id)
                ->where('type', 'IRR_STATE_SNAPSHOT')
                ->exists();

            if ($exists) {
                continue;
            }

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'IRR_STATE_SNAPSHOT',
                'payload_json' => [
                    'pump_main' => false,
                    'valve_clean_fill' => false,
                    'valve_clean_supply' => false,
                    'valve_solution_fill' => false,
                    'valve_solution_supply' => false,
                    'valve_irrigation' => false,
                    'clean_level_max' => false,
                    'clean_level_min' => false,
                    'solution_level_max' => false,
                    'solution_level_min' => false,
                    'source' => 'seed',
                ],
                'server_ts' => $now->timestamp * 1000,
                'entity_type' => 'zone',
                'entity_id' => (string) $zone->id,
            ]);

            $seeded++;
        }

        $this->command->info("IRR_STATE_SNAPSHOT events seeded for {$seeded} zones (skipped existing)");
    }

    /**
     * @return array<string, mixed>
     */
    private function defaultCommandPlans(): array
    {
        return [
            'schema_version' => 1,
            'plan_version' => 1,
            'source' => 'seed',
            'plans' => [
                'diagnostics' => [
                    'execution' => [
                        'workflow' => 'cycle_start',
                        'topology' => 'two_tank_drip_substrate_trays',
                        'required_node_types' => ['irrig'],
                        'startup' => [
                            'telemetry_max_age_sec' => 60,
                            'irr_state_max_age_sec' => 30,
                            'irr_state_wait_timeout_sec' => 5.0,
                            'sensor_mode_stabilization_time_sec' => 10,
                            'level_poll_interval_sec' => 10,
                            'clean_fill_timeout_sec' => 300,
                            'solution_fill_timeout_sec' => 600,
                            'prepare_recirculation_timeout_sec' => 300,
                            'clean_max_sensor_labels' => ['level_clean_max'],
                            'clean_min_sensor_labels' => ['level_clean_min'],
                            'solution_max_sensor_labels' => ['level_solution_max'],
                            'solution_min_sensor_labels' => ['level_solution_min'],
                        ],
                    ],
                    'steps' => [
                        ['channel' => 'storage_state', 'cmd' => 'state', 'params' => []],
                    ],
                ],
            ],
        ];
    }
}
