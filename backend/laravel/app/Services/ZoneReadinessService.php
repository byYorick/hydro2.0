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
     * Получить список обязательных bindings для зоны.
     * 
     * В E2E режиме возвращает пустой массив для гибкости тестирования.
     * В production режиме использует конфигурацию из config/zones.php.
     * 
     * @return array
     */
    private function getRequiredBindings(): array
    {
        // E2E режим - отключаем обязательные проверки
        if (config('zones.readiness.e2e_mode', false) || env('APP_ENV') === 'e2e') {
            return [];
        }

        // Получаем из конфигурации
        $requiredBindings = config('zones.readiness.required_bindings', ['main_pump']);
        
        // Если strict_mode отключен - возвращаем пустой массив
        if (!config('zones.readiness.strict_mode', true)) {
            return [];
        }

        return $requiredBindings;
    }

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

        // Проверка 1: Required bindings (только если strict_mode включен)
        $requiredBindings = $this->getRequiredBindings();
        if (!empty($requiredBindings)) {
            $missingBindings = $this->checkRequiredBindings($zone, $requiredBindings);
            if (!empty($missingBindings)) {
                $errors[] = [
                    'type' => 'missing_bindings',
                    'message' => 'Required bindings are missing: ' . implode(', ', $missingBindings),
                    'bindings' => $missingBindings,
                    'required' => $requiredBindings
                ];
            }
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
     * @param array $requiredBindings Список обязательных bindings
     * @return array Список отсутствующих bindings
     */
    private function checkRequiredBindings(Zone $zone, array $requiredBindings): array
    {
        // Если список пуст - ничего не проверяем
        if (empty($requiredBindings)) {
            return [];
        }

        // Проверяем наличие таблицы zone_channel_bindings
        if (!DB::getSchemaBuilder()->hasTable('zone_channel_bindings')) {
            // Таблица не существует, пропускаем проверку (для обратной совместимости)
            Log::warning('zone_channel_bindings table does not exist, skipping bindings check', [
                'zone_id' => $zone->id,
                'required_bindings' => $requiredBindings
            ]);
            return [];
        }

        $existingBindings = DB::table('zone_channel_bindings')
            ->where('zone_id', $zone->id)
            ->whereIn('role', $requiredBindings)
            ->pluck('role')
            ->toArray();

        $missingBindings = array_diff($requiredBindings, $existingBindings);
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
