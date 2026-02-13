<?php

namespace App\Helpers;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;

/**
 * Helper для проверки доступа пользователя к зонам, теплицам и нодам.
 *
 * Режимы работы задаются через ACCESS_CONTROL_MODE:
 * - legacy: историческое поведение (non-admin видят все зоны/теплицы).
 * - shadow: возвращает legacy-решение и логирует расхождения со strict.
 * - enforce: strict-доступ через user_zones/user_greenhouses.
 *
 * При отсутствии pivot-таблиц helper безопасно падает обратно в legacy.
 */
class ZoneAccessHelper
{
    private const MODE_LEGACY = 'legacy';

    private const MODE_SHADOW = 'shadow';

    private const MODE_ENFORCE = 'enforce';

    private const SHADOW_LOG_LIMIT = 25;

    private static int $shadowMismatchLogs = 0;

    private static bool $schemaWarningLogged = false;

    private static bool $enforceFallbackLogged = false;

    private static bool $shadowLoggerFallbackLogged = false;

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

        $legacyAllowed = true;
        $strictAllowed = self::canAccessZoneStrict($user, $zoneModel);

        return self::resolveBooleanDecision(
            resource: 'zone',
            userId: (int) $user->id,
            resourceId: (int) $zoneModel->id,
            legacyAllowed: $legacyAllowed,
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

        // Нода без зоны - пока разрешаем доступ всем авторизованным
        // В будущем можно добавить отдельную проверку
        return true;
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

        $legacyAllowed = true;
        $strictAllowed = self::canAccessGreenhouseStrict($user, $greenhouseModel);

        return self::resolveBooleanDecision(
            resource: 'greenhouse',
            userId: (int) $user->id,
            resourceId: (int) $greenhouseModel->id,
            legacyAllowed: $legacyAllowed,
            strictAllowed: $strictAllowed
        );
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

        $legacyZoneIds = Zone::pluck('id')->toArray();
        $strictZoneIds = self::getAccessibleZoneIdsStrict($user);

        return self::resolveZoneIdsDecision((int) $user->id, $legacyZoneIds, $strictZoneIds);
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

        // Получаем доступные зоны
        $zoneIds = self::getAccessibleZoneIds($user);

        $query = DeviceNode::query();

        if ($zoneIds !== []) {
            $query->whereIn('zone_id', $zoneIds);
        } else {
            $query->whereRaw('1 = 0');
        }

        // В legacy/shadow оставляем историческое поведение для нод без зоны.
        if (self::shouldExposeUnassignedNodes()) {
            $query->orWhereNull('zone_id');
        }

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

    private static function resolveBooleanDecision(
        string $resource,
        int $userId,
        int $resourceId,
        bool $legacyAllowed,
        ?bool $strictAllowed
    ): bool {
        $mode = self::accessMode();
        if ($mode === self::MODE_LEGACY) {
            return $legacyAllowed;
        }

        if ($strictAllowed === null) {
            self::logEnforceFallbackIfNeeded($mode, $resource, $userId, $resourceId);

            return $legacyAllowed;
        }

        if ($mode === self::MODE_SHADOW) {
            self::logShadowMismatchIfNeeded($resource, $userId, $resourceId, $legacyAllowed, $strictAllowed);

            return $legacyAllowed;
        }

        return $strictAllowed;
    }

    private static function resolveZoneIdsDecision(int $userId, array $legacyZoneIds, ?array $strictZoneIds): array
    {
        sort($legacyZoneIds);
        $mode = self::accessMode();

        if ($mode === self::MODE_LEGACY) {
            return $legacyZoneIds;
        }

        if ($strictZoneIds === null) {
            self::logEnforceFallbackIfNeeded($mode, 'zone_list', $userId, null);

            return $legacyZoneIds;
        }

        if ($mode === self::MODE_SHADOW) {
            if ($legacyZoneIds !== $strictZoneIds) {
                self::logShadowMismatchIfNeeded(
                    'zone_list',
                    $userId,
                    null,
                    count($legacyZoneIds),
                    count($strictZoneIds)
                );
            }

            return $legacyZoneIds;
        }

        return $strictZoneIds;
    }

    private static function shouldExposeUnassignedNodes(): bool
    {
        return self::accessMode() !== self::MODE_ENFORCE;
    }

    private static function accessMode(): string
    {
        $mode = strtolower((string) Config::get('access_control.mode', self::MODE_LEGACY));
        if (! in_array($mode, [self::MODE_LEGACY, self::MODE_SHADOW, self::MODE_ENFORCE], true)) {
            return self::MODE_LEGACY;
        }

        return $mode;
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

    private static function logShadowMismatchIfNeeded(
        string $resource,
        int $userId,
        ?int $resourceId,
        mixed $legacyValue,
        mixed $strictValue
    ): void {
        if (self::$shadowMismatchLogs >= self::SHADOW_LOG_LIMIT) {
            return;
        }

        self::$shadowMismatchLogs++;

        self::shadowLogger()->notice('ZoneAccessHelper: shadow mismatch detected', [
            'resource' => $resource,
            'user_id' => $userId,
            'resource_id' => $resourceId,
            'legacy_value' => $legacyValue,
            'strict_value' => $strictValue,
            'mode' => self::MODE_SHADOW,
            'logged_mismatches' => self::$shadowMismatchLogs,
        ]);
    }

    private static function logEnforceFallbackIfNeeded(
        string $mode,
        string $resource,
        int $userId,
        ?int $resourceId
    ): void {
        if ($mode !== self::MODE_ENFORCE || self::$enforceFallbackLogged) {
            return;
        }

        self::$enforceFallbackLogged = true;
        self::shadowLogger()->warning('ZoneAccessHelper: enforce mode fallback to legacy because assignment tables are unavailable', [
            'resource' => $resource,
            'user_id' => $userId,
            'resource_id' => $resourceId,
            'mode' => $mode,
        ]);
    }

    private static function shadowLogger()
    {
        $channel = (string) Config::get('access_control.shadow_log_channel', 'access_shadow');

        try {
            return Log::channel($channel);
        } catch (\Throwable $e) {
            if (! self::$shadowLoggerFallbackLogged) {
                self::$shadowLoggerFallbackLogged = true;
                Log::warning('ZoneAccessHelper: unable to use shadow audit channel, fallback to default', [
                    'channel' => $channel,
                    'error' => $e->getMessage(),
                ]);
            }

            return Log::channel(config('logging.default'));
        }
    }
}
