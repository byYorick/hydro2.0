<?php

namespace App\Services;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class AccessControlAssignmentService
{
    public function assignGreenhouseToAllNonAdminUsers(int|Greenhouse $greenhouse): void
    {
        if (! Schema::hasTable('user_greenhouses')) {
            return;
        }

        $greenhouseId = $greenhouse instanceof Greenhouse ? (int) $greenhouse->id : (int) $greenhouse;
        if ($greenhouseId <= 0) {
            return;
        }

        $userIds = $this->nonAdminUserIds();
        if ($userIds === []) {
            return;
        }

        $now = now();
        $rows = array_map(
            static fn (int $userId): array => [
                'user_id' => $userId,
                'greenhouse_id' => $greenhouseId,
                'created_at' => $now,
                'updated_at' => $now,
            ],
            $userIds
        );

        DB::table('user_greenhouses')->insertOrIgnore($rows);
    }

    public function assignZoneToAllNonAdminUsers(int|Zone $zone, bool $includeParentGreenhouse = true): void
    {
        if (! Schema::hasTable('user_zones')) {
            return;
        }

        $zoneModel = $zone instanceof Zone ? $zone : Zone::query()->find($zone);
        if (! $zoneModel) {
            return;
        }

        $userIds = $this->nonAdminUserIds();
        if ($userIds === []) {
            return;
        }

        if ($includeParentGreenhouse && $zoneModel->greenhouse_id) {
            $this->assignGreenhouseToAllNonAdminUsers((int) $zoneModel->greenhouse_id);
        }

        $now = now();
        $rows = array_map(
            static fn (int $userId): array => [
                'user_id' => $userId,
                'zone_id' => (int) $zoneModel->id,
                'created_at' => $now,
                'updated_at' => $now,
            ],
            $userIds
        );

        DB::table('user_zones')->insertOrIgnore($rows);
    }

    public function assignExistingTopologyToUser(User $user): void
    {
        if ($user->isAdmin()) {
            return;
        }

        $now = now();

        if (Schema::hasTable('user_greenhouses')) {
            $greenhouseIds = Greenhouse::query()->pluck('id')->map(static fn ($id): int => (int) $id)->all();
            if ($greenhouseIds !== []) {
                $rows = array_map(
                    static fn (int $greenhouseId): array => [
                        'user_id' => (int) $user->id,
                        'greenhouse_id' => $greenhouseId,
                        'created_at' => $now,
                        'updated_at' => $now,
                    ],
                    $greenhouseIds
                );
                DB::table('user_greenhouses')->insertOrIgnore($rows);
            }
        }

        if (Schema::hasTable('user_zones')) {
            $zoneIds = Zone::query()->pluck('id')->map(static fn ($id): int => (int) $id)->all();
            if ($zoneIds !== []) {
                $rows = array_map(
                    static fn (int $zoneId): array => [
                        'user_id' => (int) $user->id,
                        'zone_id' => $zoneId,
                        'created_at' => $now,
                        'updated_at' => $now,
                    ],
                    $zoneIds
                );
                DB::table('user_zones')->insertOrIgnore($rows);
            }
        }
    }

    /**
     * @return array<int>
     */
    private function nonAdminUserIds(): array
    {
        return User::query()
            ->where('role', '!=', 'admin')
            ->pluck('id')
            ->map(static fn ($id): int => (int) $id)
            ->all();
    }
}
