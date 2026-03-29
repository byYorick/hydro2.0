<?php

namespace App\Helpers;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;

/**
 * Helper для проверки доступа пользователя к зонам, теплицам и нодам.
 *
 * Доступ определяется только через strict ACL на базе user_zones/user_greenhouses.
 * При отсутствии pivot-таблиц helper работает fail-closed.
 */
class ZoneAccessHelper
{
    private static bool $schemaWarningLogged = false;

    private static bool $strictDataUnavailableLogged = false;

    /**
     * Агроном и админ могут видеть узлы без привязки к зоне,
     * чтобы завершать provisioning/attach flow в UI.
     */
    public static function canViewUnassignedNodes(User $user): bool
    {
        return $user->isAdmin() || $user->role === 'agronomist';
    }

    /**
     * Проверяет, имеет ли пользователь доступ к зоне.
     *
     * @param  int|Zone  $zone  Zone ID или Zone модель
     */
    public static function canAccessZone(User $user, int|Zone $zone): bool
    {
        // Админы имеют доступ ко всем зонам
        if ($user->isAdmin()) {
            return true;
        }

        // Получаем Zone модель, если передан ID
        $zoneModel = $zone instanceof Zone ? $zone : Zone::find($zone);
        if (! $zoneModel) {
            return false;
        }

        $strictAllowed = self::canAccessZoneStrict($user, $zoneModel);

        return self::resolveBooleanDecision(
            resource: 'zone',
            userId: (int) $user->id,
            resourceId: (int) $zoneModel->id,
            strictAllowed: $strictAllowed
        );
    }

    /**
     * Проверяет, имеет ли пользователь доступ к ноде.
     *
     * @param  int|DeviceNode  $node  Node ID или DeviceNode модель
     */
    public static function canAccessNode(User $user, int|DeviceNode $node): bool
    {
        // Админы имеют доступ ко всем нодам
        if ($user->isAdmin()) {
            return true;
        }

        // Получаем DeviceNode модель, если передан ID
        $nodeModel = $node instanceof DeviceNode ? $node : DeviceNode::find($node);
        if (! $nodeModel) {
            return false;
        }

        // Если нода привязана к зоне, проверяем доступ через зону
        if ($nodeModel->zone_id) {
            return self::canAccessZone($user, $nodeModel->zone_id);
        }

        return self::canViewUnassignedNodes($user);
    }

    /**
     * Проверяет, имеет ли пользователь доступ к теплице.
     *
     * @param  int|Greenhouse  $greenhouse  Greenhouse ID или Greenhouse модель
     */
    public static function canAccessGreenhouse(User $user, int|Greenhouse $greenhouse): bool
    {
        // Админы имеют доступ ко всем теплицам
        if ($user->isAdmin()) {
            return true;
        }

        // Получаем Greenhouse модель, если передан ID
        $greenhouseModel = $greenhouse instanceof Greenhouse ? $greenhouse : Greenhouse::find($greenhouse);
        if (! $greenhouseModel) {
            return false;
        }

        $strictAllowed = self::canAccessGreenhouseStrict($user, $greenhouseModel);

        return self::resolveBooleanDecision(
            resource: 'greenhouse',
            userId: (int) $user->id,
            resourceId: (int) $greenhouseModel->id,
            strictAllowed: $strictAllowed
        );
    }

    /**
     * Доступ к greenhouse-scoped setup/automation flows:
     * - admin/agronomist могут работать с теплицей на этапе provisioning;
     * - остальные роли должны иметь либо direct greenhouse ACL, либо доступ хотя бы к одной зоне внутри теплицы.
     *
     * @param  int|Greenhouse  $greenhouse  Greenhouse ID или Greenhouse модель
     */
    public static function canAccessGreenhouseScope(User $user, int|Greenhouse $greenhouse): bool
    {
        if ($user->isAdmin() || $user->role === 'agronomist') {
            return true;
        }

        $greenhouseModel = $greenhouse instanceof Greenhouse ? $greenhouse : Greenhouse::find($greenhouse);
        if (! $greenhouseModel) {
            return false;
        }

        if (self::canAccessGreenhouse($user, $greenhouseModel)) {
            return true;
        }

        $accessibleZoneIds = self::getAccessibleZoneIds($user);
        if ($accessibleZoneIds === []) {
            return false;
        }

        return Zone::query()
            ->where('greenhouse_id', $greenhouseModel->id)
            ->whereIn('id', $accessibleZoneIds)
            ->exists();
    }

    /**
     * Получает список ID зон, к которым пользователь имеет доступ.
     *
     * @return array<int> Массив ID зон
     */
    public static function getAccessibleZoneIds(User $user): array
    {
        // Админы имеют доступ ко всем зонам
        if ($user->isAdmin()) {
            return Zone::pluck('id')->toArray();
        }

        $strictZoneIds = self::getAccessibleZoneIdsStrict($user);

        return self::resolveZoneIdsDecision((int) $user->id, $strictZoneIds);
    }

    /**
     * Получает список ID теплиц, к которым пользователь имеет прямой strict ACL доступ.
     *
     * @return array<int>
     */
    public static function getAccessibleGreenhouseIds(User $user): array
    {
        if ($user->isAdmin()) {
            return Greenhouse::pluck('id')->toArray();
        }

        $strictGreenhouseIds = self::getAccessibleGreenhouseIdsStrict($user);

        return self::resolveGreenhouseIdsDecision((int) $user->id, $strictGreenhouseIds);
    }

    /**
     * Получает список ID нод, к которым пользователь имеет доступ.
     *
     * @return array<int> Массив ID нод
     */
    public static function getAccessibleNodeIds(User $user): array
    {
        // Админы имеют доступ ко всем нодам
        if ($user->isAdmin()) {
            return DeviceNode::pluck('id')->toArray();
        }

        $zoneIds = self::getAccessibleZoneIds($user);
        $canViewUnassignedNodes = self::canViewUnassignedNodes($user);

        if ($zoneIds === [] && ! $canViewUnassignedNodes) {
            return [];
        }

        $query = DeviceNode::query();

        $query->where(function ($nodeQuery) use ($zoneIds, $canViewUnassignedNodes) {
            if ($zoneIds !== []) {
                $nodeQuery->whereIn('zone_id', $zoneIds);
            }

            if ($canViewUnassignedNodes) {
                if ($zoneIds !== []) {
                    $nodeQuery->orWhereNull('zone_id');
                } else {
                    $nodeQuery->whereNull('zone_id');
                }
            }
        });

        return $query->pluck('id')->toArray();
    }

    private static function canAccessZoneStrict(User $user, Zone $zone): ?bool
    {
        $hasUserZones = self::hasTable('user_zones');
        $hasUserGreenhouses = self::hasTable('user_greenhouses');

        if (! $hasUserZones && ! $hasUserGreenhouses) {
            return null;
        }

        if ($hasUserZones && $user->zones()->where('zones.id', $zone->id)->exists()) {
            return true;
        }

        if (
            $hasUserGreenhouses
            && $zone->greenhouse_id
            && $user->greenhouses()->where('greenhouses.id', $zone->greenhouse_id)->exists()
        ) {
            return true;
        }

        return false;
    }

    private static function canAccessGreenhouseStrict(User $user, Greenhouse $greenhouse): ?bool
    {
        if (! self::hasTable('user_greenhouses')) {
            return null;
        }

        return $user->greenhouses()->where('greenhouses.id', $greenhouse->id)->exists();
    }

    private static function getAccessibleZoneIdsStrict(User $user): ?array
    {
        $hasUserZones = self::hasTable('user_zones');
        $hasUserGreenhouses = self::hasTable('user_greenhouses');

        if (! $hasUserZones && ! $hasUserGreenhouses) {
            return null;
        }

        $zoneIds = [];

        if ($hasUserZones) {
            $zoneIds = array_merge($zoneIds, $user->zones()->pluck('zones.id')->toArray());
        }

        if ($hasUserGreenhouses) {
            $greenhouseIds = $user->greenhouses()->pluck('greenhouses.id')->toArray();
            if ($greenhouseIds !== []) {
                $zoneIds = array_merge(
                    $zoneIds,
                    Zone::whereIn('greenhouse_id', $greenhouseIds)->pluck('id')->toArray()
                );
            }
        }

        $zoneIds = array_values(array_unique(array_map('intval', $zoneIds)));
        sort($zoneIds);

        return $zoneIds;
    }

    private static function getAccessibleGreenhouseIdsStrict(User $user): ?array
    {
        if (! self::hasTable('user_greenhouses')) {
            return null;
        }

        $greenhouseIds = $user->greenhouses()->pluck('greenhouses.id')->toArray();
        $greenhouseIds = array_values(array_unique(array_map('intval', $greenhouseIds)));
        sort($greenhouseIds);

        return $greenhouseIds;
    }

    private static function resolveBooleanDecision(
        string $resource,
        int $userId,
        int $resourceId,
        ?bool $strictAllowed
    ): bool {
        if ($strictAllowed === null) {
            self::logStrictDataUnavailableIfNeeded($resource, $userId, $resourceId);
            return false;
        }

        return $strictAllowed;
    }

    private static function resolveZoneIdsDecision(int $userId, ?array $strictZoneIds): array
    {
        if ($strictZoneIds === null) {
            self::logStrictDataUnavailableIfNeeded('zone_list', $userId, null);
            return [];
        }

        return $strictZoneIds;
    }

    private static function resolveGreenhouseIdsDecision(int $userId, ?array $strictGreenhouseIds): array
    {
        if ($strictGreenhouseIds === null) {
            self::logStrictDataUnavailableIfNeeded('greenhouse_list', $userId, null);
            return [];
        }

        return $strictGreenhouseIds;
    }

    private static function hasTable(string $table): bool
    {
        try {
            return Schema::hasTable($table);
        } catch (\Throwable $e) {
            if (! self::$schemaWarningLogged) {
                self::$schemaWarningLogged = true;
                Log::warning('ZoneAccessHelper: failed to check schema table existence', [
                    'table' => $table,
                    'error' => $e->getMessage(),
                ]);
            }

            return false;
        }
    }

    private static function logStrictDataUnavailableIfNeeded(
        string $resource,
        int $userId,
        ?int $resourceId
    ): void {
        if (self::$strictDataUnavailableLogged) {
            return;
        }

        self::$strictDataUnavailableLogged = true;
        Log::warning('ZoneAccessHelper: strict access data unavailable, applying fail-closed decision', [
            'resource' => $resource,
            'user_id' => $userId,
            'resource_id' => $resourceId,
        ]);
    }
}
