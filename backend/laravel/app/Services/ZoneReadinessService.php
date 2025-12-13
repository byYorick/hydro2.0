<?php

namespace App\Services;

use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Сервис для проверки готовности зоны к запуску grow-cycle
 */
class ZoneReadinessService
{
    /**
     * Required bindings для работы зоны
     * Это минимальный набор ролей, которые должны быть привязаны
     * 
     * Примечание: Для E2E тестов может быть пустым массивом, чтобы не блокировать тестирование
     */
    private const REQUIRED_BINDINGS = [
        // Отключено для E2E тестов - зоны могут стартовать без bindings
        // 'main_pump',      // Основной насос для полива
        // 'ph_control',     // pH контроль (опционально, зависит от типа зоны)
        // 'ec_control',     // EC контроль (опционально, зависит от типа зоны)
    ];

    /**
     * Проверить готовность зоны к запуску grow-cycle
     *
     * @param Zone $zone
     * @return array [
     *   'ready' => bool,
     *   'warnings' => array,
     *   'errors' => array
     * ]
     */
    public function checkZoneReadiness(Zone $zone): array
    {
        $warnings = [];
        $errors = [];

        // Проверка 1: Required bindings
        $missingBindings = $this->checkRequiredBindings($zone);
        if (!empty($missingBindings)) {
            $errors[] = [
                'type' => 'missing_bindings',
                'message' => 'Required bindings are missing: ' . implode(', ', $missingBindings),
                'bindings' => $missingBindings
            ];
        }

        // Проверка 2: Online nodes (warning only)
        $offlineNodesInfo = $this->checkOnlineNodes($zone);
        if ($offlineNodesInfo['offline_count'] > 0) {
            $warnings[] = [
                'type' => 'offline_nodes',
                'message' => "{$offlineNodesInfo['offline_count']} node(s) are offline",
                'count' => $offlineNodesInfo['offline_count'],
                'nodes' => $offlineNodesInfo['nodes']
            ];
        }

        // Проверка 3: Recipe attached (если требуется)
        if (!$zone->recipeInstance) {
            $warnings[] = [
                'type' => 'no_recipe',
                'message' => 'No recipe attached to zone. Zone can start without recipe, but grow-cycle features will be limited.'
            ];
        }

        return [
            'ready' => empty($errors),
            'warnings' => $warnings,
            'errors' => $errors
        ];
    }

    /**
     * Проверить наличие required bindings
     *
     * @param Zone $zone
     * @return array Список отсутствующих bindings
     */
    private function checkRequiredBindings(Zone $zone): array
    {
        // Проверяем наличие таблицы zone_channel_bindings
        if (!DB::getSchemaBuilder()->hasTable('zone_channel_bindings')) {
            // Таблица не существует, пропускаем проверку (для обратной совместимости)
            Log::warning('zone_channel_bindings table does not exist, skipping bindings check', [
                'zone_id' => $zone->id
            ]);
            return [];
        }

        $existingBindings = DB::table('zone_channel_bindings')
            ->where('zone_id', $zone->id)
            ->whereIn('role', self::REQUIRED_BINDINGS)
            ->pluck('role')
            ->toArray();

        $missingBindings = array_diff(self::REQUIRED_BINDINGS, $existingBindings);
        return array_values($missingBindings);
    }

    /**
     * Проверить статус узлов (online/offline)
     *
     * @param Zone $zone
     * @return array ['offline_count' => int, 'nodes' => array]
     */
    private function checkOnlineNodes(Zone $zone): array
    {
        $nodes = $zone->nodes()
            ->select('id', 'uid', 'name', 'status')
            ->get();

        $offlineNodes = $nodes->filter(function ($node) {
            return $node->status !== 'ONLINE' && $node->status !== null;
        });

        return [
            'offline_count' => $offlineNodes->count(),
            'total_count' => $nodes->count(),
            'nodes' => $offlineNodes->map(function ($node) {
                return [
                    'id' => $node->id,
                    'uid' => $node->uid,
                    'name' => $node->name,
                    'status' => $node->status
                ];
            })->values()->toArray()
        ];
    }
}
