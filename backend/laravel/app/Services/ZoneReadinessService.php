<?php

namespace App\Services;

use App\Models\Alert;
use App\Models\ChannelBinding;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Сервис для проверки готовности зоны к запуску grow-cycle
 */
class ZoneReadinessService
{
    private const PH_REQUIRED_BINDINGS = [
        'ph_acid_pump',
        'ph_base_pump',
    ];

    private const EC_REQUIRED_BINDINGS = [
        'ec_npk_pump',
        'ec_calcium_pump',
        'ec_magnesium_pump',
        'ec_micro_pump',
    ];

    /**
     * Получить список обязательных bindings для зоны.
     *
     * В E2E режиме возвращает пустой массив для гибкости тестирования.
     * В production режиме использует конфигурацию из config/zones.php.
     */
    private function getRequiredBindings(Zone $zone): array
    {
        // В E2E режиме strict-проверки можно отключать полностью для изолированных тестовых сценариев.
        $env = env('APP_ENV', 'production');
        if (config('zones.readiness.e2e_mode', false) || $env === 'e2e') {
            return [];
        }

        // Если strict_mode отключен - возвращаем пустой массив
        if (! config('zones.readiness.strict_mode', true)) {
            return [];
        }

        $configured = config('zones.readiness.required_bindings', ['main_pump', 'drain']);
        if (is_string($configured)) {
            $configured = array_filter(array_map('trim', explode(',', $configured)));
        }
        if (! is_array($configured)) {
            $configured = ['main_pump', 'drain'];
        }

        return array_values(array_unique(array_merge(
            $configured,
            $this->getCapabilityRequiredBindings($zone)
        )));
    }

    /**
     * Получить обязательные роли по включённым capability зоны.
     */
    private function getCapabilityRequiredBindings(Zone $zone): array
    {
        $capabilities = is_array($zone->capabilities) ? $zone->capabilities : [];
        $required = [];

        if ($this->isCapabilityEnabled($capabilities['ph_control'] ?? false)) {
            $required = array_merge($required, self::PH_REQUIRED_BINDINGS);
        }

        if ($this->isCapabilityEnabled($capabilities['ec_control'] ?? false)) {
            $required = array_merge($required, self::EC_REQUIRED_BINDINGS);
        }

        return $required;
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
        $warningDetails = [];
        $errorDetails = [];
        $optionalAssets = [
            'light' => false,
            'vent' => false,
            'heater' => false,
            'mist' => false,
        ];

        $nodesInfo = $this->checkOnlineNodes($zone);
        $hasNodes = $nodesInfo['total_count'] > 0;
        $hasOnlineNodes = $nodesInfo['online_count'] > 0;

        if (! $hasNodes) {
            $errorDetails[] = [
                'type' => 'no_nodes',
                'message' => 'Zone has no bound nodes',
            ];
        }

        if ($hasNodes && ! $hasOnlineNodes) {
            $errorDetails[] = [
                'type' => 'no_online_nodes',
                'message' => 'Zone has no online nodes',
            ];
        }

        // Проверка 1: Required bindings (только если strict_mode включен)
        $requiredBindings = $this->getRequiredBindings($zone);
        $missingBindings = [];
        if (! empty($requiredBindings)) {
            $missingBindings = $this->checkRequiredBindings($zone, $requiredBindings);
            if (! empty($missingBindings)) {
                $errorDetails[] = [
                    'type' => 'missing_bindings',
                    'message' => 'Required bindings are missing: '.implode(', ', $missingBindings),
                    'bindings' => $missingBindings,
                    'required' => $requiredBindings,
                ];
            }
        }

        // Проверка 2: Online nodes (warning only)
        if ($nodesInfo['offline_count'] > 0) {
            $warningDetails[] = [
                'type' => 'offline_nodes',
                'message' => "{$nodesInfo['offline_count']} node(s) are offline",
                'count' => $nodesInfo['offline_count'],
                'nodes' => $nodesInfo['nodes'],
            ];
        }

        $requiredAssets = [];
        foreach ($requiredBindings as $role) {
            $requiredAssets[$role] = ! in_array($role, $missingBindings, true);
        }

        $checks = array_merge($requiredAssets, [
            'has_nodes' => $hasNodes,
            'online_nodes' => $hasOnlineNodes,
        ]);

        return [
            'ready' => empty($errorDetails),
            'warnings' => $this->extractMessages($warningDetails),
            'errors' => $this->extractMessages($errorDetails),
            'warning_details' => $warningDetails,
            'error_details' => $errorDetails,
            'required_bindings' => $requiredBindings,
            'missing_bindings' => $missingBindings,
            'required_assets' => $requiredAssets,
            'optional_assets' => $optionalAssets,
            'nodes' => [
                'online' => $nodesInfo['online_count'],
                'total' => $nodesInfo['total_count'],
                'all_online' => $nodesInfo['offline_count'] === 0 && $nodesInfo['total_count'] > 0,
            ],
            'checks' => $checks,
        ];
    }

    /**
     * Legacy-совместимый метод для контроллеров инфраструктуры/команд.
     *
     * @return array{
     *   valid: bool,
     *   ready: bool,
     *   warnings: array<int, string>,
     *   errors: array<int, string>,
     *   details: array<string, mixed>
     * }
     */
    public function validate(int $zoneId): array
    {
        $zone = Zone::query()->find($zoneId);
        if (! $zone) {
            return [
                'valid' => false,
                'ready' => false,
                'warnings' => [],
                'errors' => ['Zone not found'],
                'details' => [],
            ];
        }

        $readiness = $this->checkZoneReadiness($zone);

        return [
            'valid' => $readiness['ready'],
            'ready' => $readiness['ready'],
            'warnings' => $this->extractMessages($readiness['warnings']),
            'errors' => $this->extractMessages($readiness['errors']),
            'details' => $readiness,
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
        $nodesOnline = $nodes->filter(function ($node) {
            return is_string($node->status) && strtolower($node->status) === 'online';
        })->count();

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

        if (! DB::getSchemaBuilder()->hasTable('channel_bindings')) {
            Log::error('channel_bindings table does not exist; readiness check is fail-closed', [
                'zone_id' => $zone->id,
                'required_bindings' => $requiredBindings,
            ]);
            return array_values($requiredBindings);
        }

        $existingBindings = ChannelBinding::query()
            ->whereIn('role', $requiredBindings)
            ->whereHas('infrastructureInstance', function ($query) use ($zone) {
                $query->where(function ($ownerQuery) use ($zone) {
                    $ownerQuery->where(function ($zoneOwner) use ($zone) {
                        $zoneOwner->where('owner_type', 'zone')
                            ->where('owner_id', $zone->id);
                    })->orWhere(function ($greenhouseOwner) use ($zone) {
                        $greenhouseOwner->where('owner_type', 'greenhouse')
                            ->where('owner_id', $zone->greenhouse_id);
                    });
                });
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
        if (! DB::getSchemaBuilder()->hasTable('channel_bindings')) {
            Log::error('channel_bindings table does not exist; readiness node check is fail-closed', [
                'zone_id' => $zone->id,
            ]);

            return [
                'online_count' => 0,
                'offline_count' => 0,
                'total_count' => 0,
                'nodes' => [],
            ];
        }

        $nodes = ChannelBinding::query()
            ->join('node_channels', 'channel_bindings.node_channel_id', '=', 'node_channels.id')
            ->join('nodes', 'node_channels.node_id', '=', 'nodes.id')
            ->join('infrastructure_instances', 'channel_bindings.infrastructure_instance_id', '=', 'infrastructure_instances.id')
            ->where(function ($query) use ($zone) {
                $query->where(function ($zoneOwner) use ($zone) {
                    $zoneOwner->where('infrastructure_instances.owner_type', 'zone')
                        ->where('infrastructure_instances.owner_id', $zone->id);
                })->orWhere(function ($greenhouseOwner) use ($zone) {
                    $greenhouseOwner->where('infrastructure_instances.owner_type', 'greenhouse')
                        ->where('infrastructure_instances.owner_id', $zone->greenhouse_id);
                });
            })
            ->select('nodes.id', 'nodes.uid', 'nodes.name', 'nodes.status')
            ->distinct()
            ->get();

        $onlineNodes = $nodes->filter(function ($node) {
            return is_string($node->status) && strtolower($node->status) === 'online';
        });

        $offlineNodes = $nodes->filter(function ($node) {
            return is_string($node->status) && strtolower($node->status) !== 'online';
        });

        return [
            'online_count' => $onlineNodes->count(),
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

    /**
     * Нормализовать список предупреждений/ошибок в массив сообщений.
     *
     * @param  array<int, mixed>  $issues
     * @return array<int, string>
     */
    private function extractMessages(array $issues): array
    {
        $messages = [];
        foreach ($issues as $issue) {
            if (is_string($issue)) {
                $messages[] = $issue;
                continue;
            }

            if (is_array($issue) && isset($issue['message']) && is_string($issue['message'])) {
                $messages[] = $issue['message'];
            }
        }

        return $messages;
    }

    /**
     * Нормализация capability-флага из bool/int/string.
     */
    private function isCapabilityEnabled(mixed $value): bool
    {
        if (is_bool($value)) {
            return $value;
        }

        if (is_int($value) || is_float($value)) {
            return (float) $value > 0;
        }

        if (is_string($value)) {
            return in_array(strtolower(trim($value)), ['1', 'true', 'yes', 'on'], true);
        }

        return false;
    }
}
