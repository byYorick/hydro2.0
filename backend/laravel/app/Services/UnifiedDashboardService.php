<?php

namespace App\Services;

use App\Helpers\ZoneAccessHelper;
use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class UnifiedDashboardService
{
    public function __construct(
        private GrowCyclePresenter $growCyclePresenter,
        private ZoneFrontendTelemetryService $zoneFrontendTelemetry,
        private ZoneIrrigationModalContextService $irrigationModalContext,
        private AlertPolicyService $alertPolicy,
    ) {}

    /**
     * @return array{summary: array, zonesData: array<int, array>, greenhouses: array<int, array>, latestAlerts: Collection<int, Alert>}
     */
    public function getData(?User $user): array
    {
        $userId = $user?->id ?? 0;
        $version = self::cacheVersion();
        $cacheKey = "unified_dashboard_{$userId}_v{$version}";

        return Cache::remember($cacheKey, 30, function () use ($user) {
            return $this->buildUncachedData($user);
        });
    }

    /**
     * Ключ счётчика версии кеша unified-дашборда. Версия включается в имя
     * кеш-ключа (`unified_dashboard_<user>_v<version>`); при инвалидации мы
     * лишь увеличиваем счётчик — старые записи протухают сами по TTL, новые
     * читаются под новым именем. Подход не требует поддержки тегов кешем
     * (работает с file/database/redis) и идемпотентен.
     */
    public const CACHE_VERSION_KEY = 'unified_dashboard_cache_version';

    /**
     * Сбросить кеш unified-дашборда. Вызывается из `AlertService` при
     * создании/резолве/ack алерта, чтобы блокировка автоматики (и `zones_blocked`
     * в summary) пересчитывалась без задержки 30 секунд.
     */
    public static function invalidate(): void
    {
        try {
            Cache::increment(self::CACHE_VERSION_KEY);
        } catch (\Throwable $e) {
            // Драйвер не поддержал increment — фолбэк через get+put.
            $current = (int) (Cache::get(self::CACHE_VERSION_KEY) ?? 0);
            Cache::forever(self::CACHE_VERSION_KEY, $current + 1);
        }
    }

    private static function cacheVersion(): int
    {
        $value = Cache::get(self::CACHE_VERSION_KEY);
        if ($value === null) {
            // Инициализируем счётчик единожды; ключ держим долго (forever),
            // потому что версия должна расти монотонно между перезапусками.
            Cache::forever(self::CACHE_VERSION_KEY, 1);

            return 1;
        }

        return (int) $value;
    }

    /**
     * @return array{summary: array, zonesData: array<int, array>, greenhouses: array<int, array>, latestAlerts: Collection<int, Alert>}
     */
    private function buildUncachedData(?User $user): array
    {
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);

        $zones = Zone::query()
            ->with([
                'greenhouse:id,name',
                'activeGrowCycle.currentPhase',
                'activeGrowCycle.recipeRevision.recipe:id,name',
                'activeGrowCycle.plant:id,name',
            ])
            ->withCount([
                'alerts as alerts_count' => function ($query) {
                    $query->where('status', 'ACTIVE');
                },
                'nodes as nodes_total',
                'nodes as nodes_online' => function ($query) {
                    $query->where('status', 'online');
                },
            ])
            ->when(! $user?->isAdmin(), fn ($q) => $q->whereIn('id', $accessibleZoneIds ?: [0]))
            ->orderByRaw("CASE status WHEN 'ALARM' THEN 1 WHEN 'WARNING' THEN 2 WHEN 'RUNNING' THEN 3 WHEN 'PAUSED' THEN 4 ELSE 5 END")
            ->orderBy('name')
            ->get();

        $zoneIds = $zones->pluck('id')->toArray();

        $telemetryByZone = $this->zoneFrontendTelemetry->getZoneSnapshots($zoneIds, true);
        $alertsByZone = $this->getAlertsByZone($zoneIds);
        $latestAlerts = $this->getLatestAlerts($user, $accessibleZoneIds);
        // Запрос к alerts для определения блокировки автоматики выполняется
        // до get*ByZone-методов, которые могут проглотить SQL-ошибку и оставить
        // транзакцию pgsql aborted (см. SQLSTATE[25P02]).
        $automationBlockByZone = $this->getAutomationBlockByZone($zoneIds);
        $workflowByZone = $this->getWorkflowStateByZone($zoneIds);
        $tankLevelsByZone = $this->getTankLevelsByZone($zoneIds);
        $irrigNodeByZone = $this->getIrrigNodeStateByZone($zoneIds);
        $zonesData = $this->formatZones(
            $zones,
            $telemetryByZone,
            $alertsByZone,
            $workflowByZone,
            $tankLevelsByZone,
            $irrigNodeByZone,
            $automationBlockByZone,
        );
        $summary = $this->buildSummary($zones, $automationBlockByZone);
        $greenhouses = $this->getGreenhouses($zones);

        return [
            'summary' => $summary,
            'zonesData' => $zonesData,
            'greenhouses' => $greenhouses,
            'latestAlerts' => $latestAlerts,
        ];
    }

    /**
     * @param  array<int>  $zoneIds
     * @return array<int, array<int, array{id: int, type: string, code: string|null, severity: string|null, source: string|null, details: string, created_at: string|null}>>
     */
    private function getAlertsByZone(array $zoneIds): array
    {
        if (empty($zoneIds)) {
            return [];
        }

        $alerts = Alert::query()
            ->whereIn('zone_id', $zoneIds)
            ->where('status', 'ACTIVE')
            ->orderBy('created_at', 'desc')
            ->get()
            ->groupBy('zone_id');

        $alertsByZone = [];
        foreach ($alerts as $zoneId => $zoneAlerts) {
            $alertsByZone[$zoneId] = $zoneAlerts->take(2)->values()->map(function ($alert) {
                return [
                    'id' => $alert->id,
                    'type' => $alert->type,
                    'code' => $alert->code,
                    'severity' => $alert->severity,
                    'source' => $alert->source,
                    'details' => is_array($alert->details)
                        ? (string) json_encode($alert->details)
                        : (string) $alert->details,
                    'created_at' => $alert->created_at?->toIso8601String(),
                ];
            })->toArray();
        }

        return $alertsByZone;
    }

    /**
     * Признак блокировки автоматики по каждой зоне на основе ACTIVE-алертов
     * с кодами из `AlertPolicyService::policyManagedCodes()`.
     *
     * @param  array<int, int>  $zoneIds
     * @return array<int, array{blocked: bool, reason_code: string|null, severity: string|null, message: string|null, since: string|null, alert_id: int|null, alerts_count: int}>
     */
    private function getAutomationBlockByZone(array $zoneIds): array
    {
        if (empty($zoneIds)) {
            return [];
        }

        $whitelist = $this->alertPolicy->policyManagedCodes();
        $normalizedWhitelist = array_values(array_filter(array_unique(array_map(
            static fn ($code) => strtolower(trim((string) $code)),
            $whitelist
        ))));
        if ($normalizedWhitelist === []) {
            return [];
        }

        try {
            $alerts = Alert::query()
                ->whereIn('zone_id', $zoneIds)
                ->where('status', 'ACTIVE')
                ->whereIn(DB::raw('LOWER(code)'), $normalizedWhitelist)
                ->orderByDesc('id')
                ->get(['id', 'zone_id', 'code', 'severity', 'details', 'created_at', 'first_seen_at']);
        } catch (\Throwable $e) {
            Log::warning('getAutomationBlockByZone failed: '.$e->getMessage());

            return [];
        }

        $bySeverityWeight = [
            'critical' => 4,
            'error' => 3,
            'warning' => 2,
            'info' => 1,
        ];

        $primaryByZone = [];
        $countByZone = [];

        foreach ($alerts as $alert) {
            $zoneId = (int) $alert->zone_id;
            $countByZone[$zoneId] = ($countByZone[$zoneId] ?? 0) + 1;

            $current = $primaryByZone[$zoneId] ?? null;
            $currentWeight = $current ? ($bySeverityWeight[strtolower((string) ($current->severity ?? ''))] ?? 0) : -1;
            $candidateWeight = $bySeverityWeight[strtolower((string) ($alert->severity ?? ''))] ?? 0;

            if ($current === null || $candidateWeight > $currentWeight) {
                $primaryByZone[$zoneId] = $alert;
            }
        }

        $result = [];
        foreach ($primaryByZone as $zoneId => $alert) {
            $details = is_array($alert->details) ? $alert->details : [];
            $message = null;
            foreach (['human_error_message', 'message', 'error_message', 'reason'] as $key) {
                $candidate = $details[$key] ?? null;
                if (is_string($candidate) && trim($candidate) !== '') {
                    $message = trim($candidate);
                    break;
                }
            }

            $since = $alert->first_seen_at instanceof \DateTimeInterface
                ? Carbon::instance($alert->first_seen_at)->toIso8601String()
                : ($alert->created_at instanceof \DateTimeInterface
                    ? Carbon::instance($alert->created_at)->toIso8601String()
                    : null);

            $result[$zoneId] = [
                'blocked' => true,
                'reason_code' => $alert->code,
                'severity' => $alert->severity,
                'message' => $message,
                'since' => $since,
                'alert_id' => (int) $alert->id,
                'alerts_count' => (int) ($countByZone[$zoneId] ?? 1),
            ];
        }

        return $result;
    }

    /**
     * @return Collection<int, Alert>
     */
    private function getLatestAlerts(?User $user, array $accessibleZoneIds)
    {
        $latestAlertsQuery = Alert::query()
            ->select(['id', 'type', 'status', 'details', 'zone_id', 'created_at'])
            ->with('zone:id,name')
            ->where('status', 'ACTIVE');

        if (! $user?->isAdmin()) {
            $latestAlertsQuery->whereIn('zone_id', $accessibleZoneIds ?: [0]);
        }

        return $latestAlertsQuery
            ->latest('id')
            ->limit(10)
            ->get();
    }

    /**
     * @param  array<int, array{blocked: bool, reason_code: string|null, severity: string|null, message: string|null, since: string|null, alert_id: int|null, alerts_count: int}>  $automationBlockByZone
     */
    private function buildSummary(Collection $zones, array $automationBlockByZone = []): array
    {
        $greenhouseIds = $zones->pluck('greenhouse_id')->filter()->unique()->values();

        $zonesBlocked = 0;
        foreach ($zones as $zone) {
            $block = $automationBlockByZone[(int) $zone->id] ?? null;
            if (is_array($block) && ! empty($block['blocked'])) {
                $zonesBlocked++;
            }
        }

        $summary = [
            'zones_total' => $zones->count(),
            'zones_running' => $zones->where('status', 'RUNNING')->count(),
            'zones_warning' => $zones->where('status', 'WARNING')->count(),
            'zones_alarm' => $zones->where('status', 'ALARM')->count(),
            'zones_blocked' => $zonesBlocked,
            'cycles_running' => 0,
            'cycles_paused' => 0,
            'cycles_planned' => 0,
            'cycles_none' => 0,
            'alerts_active' => (int) $zones->sum('alerts_count'),
            'devices_online' => (int) $zones->sum('nodes_online'),
            'devices_total' => (int) $zones->sum('nodes_total'),
            'greenhouses_count' => $greenhouseIds->count(),
        ];

        foreach ($zones as $zone) {
            $cycle = $zone->activeGrowCycle;
            if (! $cycle) {
                $summary['cycles_none']++;

                continue;
            }

            switch ($cycle->status->value) {
                case 'RUNNING':
                    $summary['cycles_running']++;
                    break;
                case 'PAUSED':
                    $summary['cycles_paused']++;
                    break;
                case 'PLANNED':
                    $summary['cycles_planned']++;
                    break;
                default:
                    break;
            }
        }

        return $summary;
    }

    /**
     * @param  array<int, array>  $telemetryByZone
     * @param  array<int, array>  $alertsByZone
     * @param  array<int, array{phase: string, label: string|null, stale: bool}>  $workflowByZone
     * @param  array<int, array{clean_percent: float|null, solution_percent: float|null, buffer_percent: float|null, clean_offline: bool, solution_offline: bool, buffer_offline: bool, clean_present: bool, solution_present: bool, buffer_present: bool, topology_count: int|null}>  $tankLevelsByZone
     * @param  array<int, array{online: bool, stale: bool, last_seen_at: string|null}|null>  $irrigNodeByZone
     * @param  array<int, array{blocked: bool, reason_code: string|null, severity: string|null, message: string|null, since: string|null, alert_id: int|null, alerts_count: int}>  $automationBlockByZone
     * @return array<int, array<string, mixed>>
     */
    private function formatZones(
        Collection $zones,
        array $telemetryByZone,
        array $alertsByZone,
        array $workflowByZone = [],
        array $tankLevelsByZone = [],
        array $irrigNodeByZone = [],
        array $automationBlockByZone = [],
    ): array {
        return $zones->map(function (Zone $zone) use ($telemetryByZone, $alertsByZone, $workflowByZone, $tankLevelsByZone, $irrigNodeByZone, $automationBlockByZone) {
            $cycle = $zone->activeGrowCycle;
            $cycleDto = $cycle ? ($this->growCyclePresenter->buildCycleDto($cycle)['cycle'] ?? null) : null;

            $recipe = null;
            if ($cycle?->recipeRevision?->recipe) {
                $recipe = [
                    'id' => $cycle->recipeRevision->recipe->id,
                    'name' => $cycle->recipeRevision->recipe->name,
                ];
            } elseif ($cycle?->recipe) {
                $recipe = [
                    'id' => $cycle->recipe->id,
                    'name' => $cycle->recipe->name,
                ];
            }

            $crop = $cycle?->plant?->name ?? $recipe['name'] ?? null;
            $ctx = $this->irrigationModalContext->buildForZone($zone);

            return [
                'id' => $zone->id,
                'name' => $zone->name,
                'status' => $zone->status,
                'greenhouse' => $zone->greenhouse ? [
                    'id' => $zone->greenhouse->id,
                    'name' => $zone->greenhouse->name,
                ] : null,
                'telemetry' => $this->normalizeTelemetrySnapshot($telemetryByZone[$zone->id] ?? []),
                'targets' => $ctx['targets'],
                'current_phase_targets' => $ctx['current_phase_targets'],
                'irrigation_correction_summary' => $ctx['irrigation_correction_summary'],
                'alerts_count' => (int) ($zone->alerts_count ?? 0),
                'alerts_preview' => $alertsByZone[$zone->id] ?? [],
                'devices' => [
                    'total' => (int) ($zone->nodes_total ?? 0),
                    'online' => (int) ($zone->nodes_online ?? 0),
                ],
                'recipe' => $recipe,
                'plant' => $cycle?->plant ? [
                    'id' => $cycle->plant->id,
                    'name' => $cycle->plant->name,
                ] : null,
                'cycle' => $cycleDto,
                'crop' => $crop,
                'system_state' => $workflowByZone[$zone->id] ?? null,
                'tank_levels' => $tankLevelsByZone[$zone->id] ?? null,
                'irrig_node' => $irrigNodeByZone[$zone->id] ?? null,
                'automation_block' => $automationBlockByZone[$zone->id] ?? null,
            ];
        })->values()->toArray();
    }

    /**
     * @param  array<int, int>  $zoneIds
     * @return array<int, array{online: bool, stale: bool, last_seen_at: string|null}|null>
     */
    private function getIrrigNodeStateByZone(array $zoneIds): array
    {
        if (empty($zoneIds)) {
            return [];
        }

        try {
            $rows = DB::table('nodes')
                ->whereIn('zone_id', $zoneIds)
                ->where(function ($query) {
                    $query
                        ->where('type', 'irrig')
                        ->orWhere('type', 'irrigation')
                        ->orWhere('type', 'valve_irrigation')
                        ->orWhere('type', 'pump')
                        ->orWhere('type', 'pump_node');
                })
                ->select(['zone_id', 'status', 'last_seen_at'])
                ->get();
        } catch (\Throwable $e) {
            Log::warning('getIrrigNodeStateByZone failed: '.$e->getMessage());

            return [];
        }

        $staleThreshold = Carbon::now()->subMinutes(2);
        $result = [];
        foreach ($zoneIds as $zoneId) {
            $result[$zoneId] = null;
        }

        foreach ($rows as $row) {
            $zoneId = (int) $row->zone_id;
            $lastSeen = $row->last_seen_at ? Carbon::parse($row->last_seen_at) : null;
            $isStale = $lastSeen === null || $lastSeen->lt($staleThreshold);
            // Для UI статуса IRR опираемся на canonical node.status.
            // last_seen_at оставляем как диагностику, но не сбрасываем online в offline только из-за stale окна.
            $isOnline = strtolower((string) ($row->status ?? 'offline')) === 'online';

            // Если есть несколько irrig-нод, выбираем наиболее «здоровую».
            if (! isset($result[$zoneId]) || $result[$zoneId] === null || ($isOnline && ! $result[$zoneId]['online'])) {
                $result[$zoneId] = [
                    'online' => $isOnline,
                    'stale' => $isStale,
                    'last_seen_at' => $lastSeen?->toIso8601String(),
                ];
            }
        }

        return $result;
    }

    /**
     * Батчем достаём текущий workflow_phase для набора зон из
     * `zone_workflow_state`. Считаем данные stale, если `updated_at`
     * старше 2 минут (workflow runtime должен писать чаще).
     *
     * @param  array<int, int>  $zoneIds
     * @return array<int, array{phase: string, label: string|null, stale: bool}>
     */
    private function getWorkflowStateByZone(array $zoneIds): array
    {
        if (empty($zoneIds)) {
            return [];
        }

        try {
            $rows = DB::table('zone_workflow_state')
                ->whereIn('zone_id', $zoneIds)
                ->select(['zone_id', 'workflow_phase', 'updated_at'])
                ->get();
        } catch (\Throwable $e) {
            Log::warning('getWorkflowStateByZone failed: '.$e->getMessage());

            return [];
        }

        $staleThreshold = Carbon::now()->subMinutes(2);
        $result = [];

        foreach ($rows as $row) {
            $phase = (string) ($row->workflow_phase ?? 'idle');
            $updatedAt = $row->updated_at ? Carbon::parse($row->updated_at) : null;
            $isStale = $updatedAt === null || $updatedAt->lt($staleThreshold);

            $result[(int) $row->zone_id] = [
                'phase' => $phase,
                'label' => $this->workflowPhaseLabel($phase),
                'stale' => $isStale,
            ];
        }

        return $result;
    }

    private function workflowPhaseLabel(string $phase): ?string
    {
        $map = [
            'idle' => 'Ожидание',
            'waiting' => 'Ожидание',
            'ready' => 'Готов',
            'preparing' => 'Подготовка',
            'startup' => 'Подготовка',
            'clean_fill' => 'Набор чистой воды',
            'solution_fill' => 'Приготовление раствора',
            'prepare_recirculation' => 'Рециркуляция перед поливом',
            'irrig_recirc' => 'Рециркуляция раствора',
            'recirculation' => 'Рециркуляция раствора',
            'irrigating' => 'Полив',
            'irrigation' => 'Полив',
            'irrigation_recovery' => 'Восстановление полива',
            'correction' => 'Коррекция',
            'harvesting' => 'Сбор',
            'diagnostics' => 'Диагностика',
            'error' => 'Ошибка',
            'failed' => 'Ошибка',
            'degraded' => 'Деградация',
        ];

        return $map[$phase] ?? ucfirst(str_replace('_', ' ', $phase));
    }

    /**
     * Батчем читаем уровни баков (clean/solution) из `telemetry_last`
     * по metric_type = WATER_LEVEL + `sensors.scope='tank'`.
     * Возвращает проценты, если известна capacity, иначе null.
     *
     * @param  array<int, int>  $zoneIds
     * @return array<int, array{clean_percent: float|null, solution_percent: float|null, buffer_percent: float|null, clean_offline: bool, solution_offline: bool, buffer_offline: bool, clean_present: bool, solution_present: bool, buffer_present: bool, topology_count: int|null}>
     */
    private function getTankLevelsByZone(array $zoneIds): array
    {
        if (empty($zoneIds)) {
            return [];
        }

        try {
            // В новой схеме у sensors нет колонки `channel`; канал хранится либо в
            // jsonb `specs->channel` (заполняет registry/seeders), либо в `label`
            // (заполняет SoilMoistureSensorBindingService и аналоги). Берём первое
            // непустое значение через COALESCE — это даёт стабильный ключ
            // clean/solution/buffer для матчинга в `groupTankChannel()`.
            $rows = DB::table('telemetry_last')
                ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
                ->whereIn('sensors.zone_id', $zoneIds)
                ->where('sensors.type', 'WATER_LEVEL')
                ->select([
                    'sensors.zone_id',
                    DB::raw("COALESCE(NULLIF(sensors.specs->>'channel', ''), sensors.label) as channel"),
                    'telemetry_last.last_value as value',
                    'telemetry_last.updated_at',
                ])
                ->get();
        } catch (\Throwable $e) {
            Log::warning('getTankLevelsByZone failed: '.$e->getMessage());

            return [];
        }

        $staleThreshold = Carbon::now()->subMinutes(5);
        $buckets = [];

        foreach ($rows as $row) {
            $zoneId = (int) $row->zone_id;
            $channel = strtolower((string) ($row->channel ?? ''));
            $value = is_numeric($row->value) ? (float) $row->value : null;
            $updatedAt = $row->updated_at ? Carbon::parse($row->updated_at) : null;
            $isStale = $updatedAt === null || $updatedAt->lt($staleThreshold);

            $buckets[$zoneId] ??= [
                'clean' => [],
                'solution' => [],
                'buffer' => [],
                'clean_present' => false,
                'solution_present' => false,
                'buffer_present' => false,
            ];

            // Группировка по назначению: clean_* → clean tank, solution_* → solution tank.
            // В fallback могут приехать русские label, поэтому учитываем и RU-токены.
            $target = null;
            if (
                str_contains($channel, 'clean')
                || str_contains($channel, 'fresh')
                || str_contains($channel, 'чист')
            ) {
                $target = 'clean';
                $buckets[$zoneId]['clean_present'] = true;
            } elseif (
                str_contains($channel, 'solution')
                || str_contains($channel, 'nutrient')
                || str_contains($channel, 'раств')
                || str_contains($channel, 'пит')
            ) {
                $target = 'solution';
                $buckets[$zoneId]['solution_present'] = true;
            } elseif (
                str_contains($channel, 'buffer')
                || str_contains($channel, 'drain')
                || str_contains($channel, 'return')
                || str_contains($channel, 'буфер')
                || str_contains($channel, 'слив')
                || str_contains($channel, 'дрен')
            ) {
                $target = 'buffer';
                $buckets[$zoneId]['buffer_present'] = true;
            }
            if ($target === null) {
                continue;
            }

            $buckets[$zoneId][$target][] = [
                'value' => $value,
                'stale' => $isStale,
            ];
        }

        $result = [];
        foreach ($buckets as $zoneId => $tanks) {
            $result[$zoneId] = [
                'clean_percent' => $this->aggregateTankPercent($tanks['clean']),
                'solution_percent' => $this->aggregateTankPercent($tanks['solution']),
                'buffer_percent' => $this->aggregateTankPercent($tanks['buffer']),
                'clean_offline' => $this->isTankOffline($tanks['clean']),
                'solution_offline' => $this->isTankOffline($tanks['solution']),
                'buffer_offline' => $this->isTankOffline($tanks['buffer']),
                'clean_present' => (bool) ($tanks['clean_present'] ?? false),
                'solution_present' => (bool) ($tanks['solution_present'] ?? false),
                'buffer_present' => (bool) ($tanks['buffer_present'] ?? false),
                'topology_count' => $this->resolveTankTopologyCount($tanks),
            ];
        }

        return $result;
    }

    /**
     * @param  array<int, array{value: float|null, stale: bool}>  $entries
     */
    private function aggregateTankPercent(array $entries): ?float
    {
        $values = array_filter(
            array_map(fn ($entry) => $entry['value'], $entries),
            fn ($v) => $v !== null
        );
        if ($values === []) {
            return null;
        }
        // WATER_LEVEL уже в % в telemetry_last — берём среднее, если несколько сенсоров.
        $avg = array_sum($values) / count($values);

        return round(max(0.0, min(100.0, $avg)), 1);
    }

    /**
     * @param  array<int, array{value: float|null, stale: bool}>  $entries
     */
    private function isTankOffline(array $entries): bool
    {
        if ($entries === []) {
            return true;
        }
        foreach ($entries as $entry) {
            if (! $entry['stale'] && $entry['value'] !== null) {
                return false;
            }
        }

        return true;
    }

    /**
     * @param  array{clean: array, solution: array, buffer: array, clean_present: bool, solution_present: bool, buffer_present: bool}  $tanks
     */
    private function resolveTankTopologyCount(array $tanks): ?int
    {
        $cleanPresent = (bool) ($tanks['clean_present'] ?? false);
        $solutionPresent = (bool) ($tanks['solution_present'] ?? false);
        $bufferPresent = (bool) ($tanks['buffer_present'] ?? false);

        if ($bufferPresent) {
            return 3;
        }
        if ($cleanPresent || $solutionPresent) {
            return 2;
        }

        return null;
    }

    /**
     * Нормализует telemetry_last под контракт фронтенда.
     *
     * @param  array<string, mixed>  $telemetry
     * @return array{ph: float|null, ec: float|null, temperature: float|null, humidity: float|null, co2: float|null, updated_at: string|null}
     */
    private function normalizeTelemetrySnapshot(array $telemetry): array
    {
        $ph = isset($telemetry['ph']) && is_numeric($telemetry['ph']) ? (float) $telemetry['ph'] : null;
        $ecRaw = isset($telemetry['ec']) && is_numeric($telemetry['ec']) ? (float) $telemetry['ec'] : null;
        $temperature = isset($telemetry['temperature']) && is_numeric($telemetry['temperature']) ? (float) $telemetry['temperature'] : null;
        $humidity = isset($telemetry['humidity']) && is_numeric($telemetry['humidity']) ? (float) $telemetry['humidity'] : null;
        $co2 = isset($telemetry['co2']) && is_numeric($telemetry['co2']) ? (float) $telemetry['co2'] : null;

        // Некоторые узлы отдают EC в µS/см. Для UI приводим к мСм/см, если значение явно «большое».
        $ec = $ecRaw;
        if ($ecRaw !== null && $ecRaw > 20.0) {
            $ec = $ecRaw / 1000.0;
        }

        $updatedAt = null;
        if (isset($telemetry['updated_at']) && is_string($telemetry['updated_at']) && $telemetry['updated_at'] !== '') {
            $updatedAt = $telemetry['updated_at'];
        } elseif (isset($telemetry['last_updated']) && is_string($telemetry['last_updated']) && $telemetry['last_updated'] !== '') {
            $updatedAt = $telemetry['last_updated'];
        }

        return [
            'ph' => $ph,
            'ec' => $ec,
            'temperature' => $temperature,
            'humidity' => $humidity,
            'co2' => $co2,
            'updated_at' => $updatedAt,
        ];
    }

    /**
     * @return array<int, array{id: int, name: string}>
     */
    private function getGreenhouses(Collection $zones): array
    {
        return $zones->map(function (Zone $zone) {
            if (! $zone->greenhouse) {
                return null;
            }

            return [
                'id' => $zone->greenhouse->id,
                'name' => $zone->greenhouse->name,
            ];
        })->filter()->unique('id')->values()->toArray();
    }
}
