<?php

namespace Database\Seeders;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class AccessControlBootstrapSeeder extends Seeder
{
    public function run(): void
    {
        if (! Schema::hasTable('user_greenhouses') || ! Schema::hasTable('user_zones')) {
            $this->command?->warn('ACL bootstrap skipped: assignment tables are unavailable.');

            return;
        }

        $greenhouseIds = Greenhouse::query()->pluck('id')->all();
        $zoneIds = Zone::query()->pluck('id')->all();

        if ($greenhouseIds === [] && $zoneIds === []) {
            $this->command?->info('ACL bootstrap skipped: no greenhouses or zones found.');

            return;
        }

        $users = User::query()
            ->where('role', '!=', 'admin')
            ->get(['id']);

        if ($users->isEmpty()) {
            $this->command?->info('ACL bootstrap skipped: no non-admin users found.');

            return;
        }

        $now = now();
        $greenhouseRows = [];
        $zoneRows = [];

        foreach ($users as $user) {
            foreach ($greenhouseIds as $greenhouseId) {
                $greenhouseRows[] = [
                    'user_id' => $user->id,
                    'greenhouse_id' => $greenhouseId,
                    'created_at' => $now,
                    'updated_at' => $now,
                ];
            }

            foreach ($zoneIds as $zoneId) {
                $zoneRows[] = [
                    'user_id' => $user->id,
                    'zone_id' => $zoneId,
                    'created_at' => $now,
                    'updated_at' => $now,
                ];
            }
        }

        if ($greenhouseRows !== []) {
            DB::table('user_greenhouses')->insertOrIgnore($greenhouseRows);
        }

        if ($zoneRows !== []) {
            DB::table('user_zones')->insertOrIgnore($zoneRows);
        }

        $this->command?->info(sprintf(
            'ACL bootstrap complete: %d users, %d greenhouses, %d zones.',
            $users->count(),
            count($greenhouseIds),
            count($zoneIds)
        ));
    }
}
