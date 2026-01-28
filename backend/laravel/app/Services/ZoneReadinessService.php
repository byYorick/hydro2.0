<?php

namespace App\Services;

use App\Models\Alert;
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
     */
    private function getRequiredBindings(): array
    {
        // E2E режим - отключаем обязательные проверки для тестового окружения
        // APP_ENV может быть 'e2e', 'testing', или 'test'
        $env = env('APP_ENV', 'production');
        if (config('zones.readiness.e2e_mode', false) || in_array($env, ['e2e', 'testing', 'test'])) {
            return [];
        }

        // Получаем из конфигурации
        $requiredBindings = config('zones.readiness.required_bindings', ['main_pump']);

        // Если strict_mode отключен - возвращаем пустой массив
        if (! config('zones.readiness.strict_mode', true)) {
            return [];
        }

        return $requiredBindings;
    }

    /**
     * Проверить готовность зоны к запуску grow-cycle
     *
     * @return array [
     *               'ready' => bool,
     *               'warnings' => array,
     *               'errors' => array
     *               ]
     */
    public function checkZoneReadiness(Zone $zone): array
    {
        $warnings = [];
        $errors = [];

        // Проверка 1: Required bindings (только если strict_mode включен)
        $requiredBindings = $this->getRequiredBindings();
        if (! empty($requiredBindings)) {
            $missingBindings = $this->checkRequiredBindings($zone, $requiredBindings);
            if (! empty($missingBindings)) {
                $errors[] = [
                    'type' => 'missing_bindings',
                    'message' => 'Required bindings are missing: '.implode(', ', $missingBindings),
                    'bindings' => $missingBindings,
                    'required' => $requiredBindings,
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
                'nodes' => $offlineNodesInfo['nodes'],
            ];
        }

        // Проверка 3: Recipe attached (если требуется)
        if (! $zone->recipeInstance) {
            $warnings[] = [
                'type' => 'no_recipe',
                'message' => 'No recipe attached to zone. Zone can start without recipe, but grow-cycle features will be limited.',
            ];
        }

        return [
            'ready' => empty($errors),
            'warnings' => $warnings,
            'errors' => $errors,
        ];
    }

    /**
     * Получить сводное состояние здоровья зоны для API.
     *
     * @return array{
     *   zone_id: int,
     *   ready: bool,
     *   warnings: array,
     *   errors: array,
     *   nodes_total: int,
     *   nodes_online: int,
     *   active_alerts_count: int
     * }
     */
    public function getZoneHealth(Zone $zone): array
    {
        $readiness = $this->checkZoneReadiness($zone);

        $nodes = $zone->nodes()
            ->select('id', 'status')
            ->get();

        $nodesTotal = $nodes->count();
        $nodesOnline = $nodes->filter(fn ($node) => $node->status === 'online')->count();

        $activeAlertsCount = Alert::query()
            ->where('zone_id', $zone->id)
            ->where('status', 'ACTIVE')
            ->count();

        return [
            'zone_id' => $zone->id,
            'ready' => $readiness['ready'],
            'warnings' => $readiness['warnings'],
            'errors' => $readiness['errors'],
            'nodes_total' => $nodesTotal,
            'nodes_online' => $nodesOnline,
            'active_alerts_count' => $activeAlertsCount,
        ];
    }

    /**
     * Проверить наличие required bindings
     *
     * @param  array  $requiredBindings  Список обязательных bindings
     * @return array Список отсутствующих bindings
     */
    private function checkRequiredBindings(Zone $zone, array $requiredBindings): array
    {
        // Если список пуст - ничего не проверяем
        if (empty($requiredBindings)) {
            return [];
        }

        // Проверяем наличие таблицы channel_bindings
        if (! DB::getSchemaBuilder()->hasTable('channel_bindings')) {
            Log::warning('channel_bindings table does not exist, skipping bindings check', [
                'zone_id' => $zone->id,
                'required_bindings' => $requiredBindings,
            ]);

            return [];
        }

        $existingBindings = \App\Models\ChannelBinding::query()
            ->whereIn('role', $requiredBindings)
            ->whereHas('infrastructureInstance', function ($query) use ($zone) {
                $query->where('owner_type', 'zone')
                    ->where('owner_id', $zone->id);
            })
            ->pluck('role')
            ->unique()
            ->toArray();

        $missingBindings = array_diff($requiredBindings, $existingBindings);

        return array_values($missingBindings);
    }

    /**
     * Проверить статус узлов (online/offline)
     *
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
                    'status' => $node->status,
                ];
            })->values()->toArray(),
        ];
    }
}
