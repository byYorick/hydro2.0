<?php

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('users') || ! Schema::hasTable('greenhouses') || ! Schema::hasTable('zones')) {
            return;
        }

        if (! Schema::hasTable('user_greenhouses') || ! Schema::hasTable('user_zones')) {
            return;
        }

        $greenhouseIds = Greenhouse::query()->pluck('id')->all();
        $zoneIds = Zone::query()->pluck('id')->all();

        if ($greenhouseIds === [] && $zoneIds === []) {
            return;
        }

        $users = User::query()
            ->where('role', '!=', 'admin')
            ->get(['id']);

        if ($users->isEmpty()) {
            return;
        }

        $now = now();

        foreach ($users as $user) {
            $hasAssignments = DB::table('user_greenhouses')->where('user_id', $user->id)->exists()
                || DB::table('user_zones')->where('user_id', $user->id)->exists();

            if ($hasAssignments) {
                continue;
            }

            $greenhouseRows = array_map(
                static fn (int $greenhouseId): array => [
                    'user_id' => $user->id,
                    'greenhouse_id' => $greenhouseId,
                    'created_at' => $now,
                    'updated_at' => $now,
                ],
                $greenhouseIds
            );

            $zoneRows = array_map(
                static fn (int $zoneId): array => [
                    'user_id' => $user->id,
                    'zone_id' => $zoneId,
                    'created_at' => $now,
                    'updated_at' => $now,
                ],
                $zoneIds
            );

            if ($greenhouseRows !== []) {
                DB::table('user_greenhouses')->insertOrIgnore($greenhouseRows);
            }

            if ($zoneRows !== []) {
                DB::table('user_zones')->insertOrIgnore($zoneRows);
            }
        }
    }

    public function down(): void
    {
        // Intentional no-op: rollback would risk deleting explicit ACL assignments
        // that may have been edited after this one-time backfill.
    }
};
