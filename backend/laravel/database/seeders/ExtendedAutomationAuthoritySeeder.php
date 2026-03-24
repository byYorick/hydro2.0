<?php

namespace Database\Seeders;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\AutomationConfigDocumentService;
use App\Services\ZoneLogicProfileCatalog;
use App\Services\ZoneLogicProfileService;
use Illuminate\Database\Seeder;

class ExtendedAutomationAuthoritySeeder extends Seeder
{
    public function run(): void
    {
        app(AutomationConfigDocumentService::class)->ensureSystemDefaults();

        $adminId = User::query()->where('role', 'admin')->value('id') ?? User::query()->value('id');
        $zones = Zone::query()->get();

        foreach ($zones as $zone) {
            app(AutomationConfigDocumentService::class)->ensureZoneDefaults((int) $zone->id);
            app(ZoneLogicProfileService::class)->upsertProfile(
                zone: $zone,
                mode: ZoneLogicProfileCatalog::MODE_WORKING,
                subsystems: $this->defaultSubsystems(),
                activate: true,
                userId: $adminId ? (int) $adminId : null,
            );
        }

        $this->seedIrrStateEvents($zones);
        $this->command?->info('Authority automation defaults seeded for '.$zones->count().' zones');
    }

    /**
     * @return array<string, mixed>
     */
    private function defaultSubsystems(): array
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

    /**
     * @param  \Illuminate\Support\Collection<int, Zone>  $zones
     */
    private function seedIrrStateEvents($zones): void
    {
        $now = now();

        foreach ($zones as $zone) {
            $exists = ZoneEvent::query()
                ->where('zone_id', $zone->id)
                ->where('type', 'IRR_STATE_SNAPSHOT')
                ->exists();

            if ($exists) {
                continue;
            }

            ZoneEvent::query()->create([
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
        }
    }
}
