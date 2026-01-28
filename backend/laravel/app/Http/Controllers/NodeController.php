<?php

namespace App\Http\Controllers;

use App\Enums\NodeLifecycleState;
use App\Http\Requests\PublishNodeConfigRequest;
use App\Http\Requests\UpdateNodeRequest;
use App\Models\DeviceNode;
use App\Services\NodeConfigService;
use App\Services\NodeLifecycleService;
use App\Services\NodeRegistryService;
use App\Services\NodeService;
use App\Services\NodeSwapService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class NodeController extends Controller
{
    public function __construct(
        private NodeService $nodeService,
        private NodeRegistryService $registryService,
        private NodeConfigService $configService,
        private NodeSwapService $swapService,
        private NodeLifecycleService $lifecycleService
    ) {}

    public function index(Request $request)
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Валидация query параметров
        $validated = $request->validate([
            'zone_id' => ['nullable', 'integer', 'exists:zones,id'],
            'status' => ['nullable', 'string'],
            'search' => ['nullable', 'string', 'max:255'],
            'new_only' => ['nullable', 'string', 'in:true,false,1,0'],
            'unassigned' => ['nullable', 'string', 'in:true,false,1,0'],
        ]);

        // Преобразуем строковые boolean значения
        if (isset($validated['new_only'])) {
            $validated['new_only'] = filter_var($validated['new_only'], FILTER_VALIDATE_BOOLEAN);
        }
        if (isset($validated['unassigned'])) {
            $validated['unassigned'] = filter_var($validated['unassigned'], FILTER_VALIDATE_BOOLEAN);
        }

        // Получаем доступные ноды для пользователя
        $accessibleNodeIds = \App\Helpers\ZoneAccessHelper::getAccessibleNodeIds($user);

        // Eager loading для предотвращения N+1 запросов
        // Исключаем config из выборки для предотвращения утечки Wi-Fi/MQTT кредов
        $query = DeviceNode::query()
            ->select('id', 'uid', 'name', 'type', 'zone_id', 'status', 'lifecycle_state', 'fw_version', 'hardware_revision', 'hardware_id', 'validated', 'first_seen_at', 'created_at', 'updated_at')
            ->with(['zone:id,name,status', 'channels' => function ($channelQuery) {
                // Исключаем config из каналов
                $channelQuery->select('id', 'node_id', 'channel', 'type', 'metric', 'unit');
            }]);

        // Фильтруем по доступным нодам (кроме админов)
        if (! $user->isAdmin()) {
            $query->whereIn('id', $accessibleNodeIds);
        }

        if (isset($validated['zone_id'])) {
            // Дополнительно проверяем доступ к зоне
            if (! $user->isAdmin() && ! \App\Helpers\ZoneAccessHelper::canAccessZone($user, $validated['zone_id'])) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this zone',
                ], 403);
            }
            $query->where('zone_id', $validated['zone_id']);
        }
        if (isset($validated['status'])) {
            $query->where('status', $validated['status']);
        }
        // Поиск новых нод (без привязки к зоне)
        if (isset($validated['new_only']) && $validated['new_only']) {
            $query->whereNull('zone_id');
        }
        // Поиск непривязанных нод (новые или без зоны)
        if (isset($validated['unassigned']) && $validated['unassigned']) {
            $query->whereNull('zone_id');
        }

        // Поиск по имени, UID или типу
        if (isset($validated['search']) && $validated['search']) {
            // Экранируем специальные символы LIKE для защиты от SQL injection
            $searchTerm = addcslashes($validated['search'], '%_');
            $query->where(function ($q) use ($searchTerm) {
                $q->where('name', 'ILIKE', "%{$searchTerm}%")
                    ->orWhere('uid', 'ILIKE', "%{$searchTerm}%")
                    ->orWhere('type', 'ILIKE', "%{$searchTerm}%");
            });
        }

        $items = $query->latest('id')->paginate(25);

        // Убираем config из результатов (на случай если он был загружен через отношения)
        $items->getCollection()->transform(function ($node) {
            unset($node->config);
            foreach ($node->channels as $channel) {
                unset($channel->config);
            }

            return $node;
        });

        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(\App\Http\Requests\StoreNodeRequest $request)
    {
        $data = $request->validated();
        $node = $this->nodeService->create($data);

        return response()->json(['status' => 'ok', 'data' => $node], Response::HTTP_CREATED);
    }

    public function show(Request $request, DeviceNode $node)
    {
        $this->authorize('view', $node);

        // Загружаем связанные данные, исключая config для предотвращения утечки Wi-Fi/MQTT кредов
        $node->load(['zone:id,name,status', 'channels' => function ($channelQuery) {
            $channelQuery->select('id', 'node_id', 'channel', 'type', 'metric', 'unit');
        }]);

        // Убираем config из ноды и каналов
        unset($node->config);
        foreach ($node->channels as $channel) {
            unset($channel->config);
        }

        return response()->json(['status' => 'ok', 'data' => $node]);
    }

    public function update(UpdateNodeRequest $request, DeviceNode $node)
    {
        $user = $this->authenticateUser($request);
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $this->authorize('update', $node);

        $data = $request->validated();

        // Проверяем доступ к новой зоне, если меняется
        $this->validateZoneChange($user, $node, $data);

        $node = $this->nodeService->update($node, $data);

        return response()->json(['status' => 'ok', 'data' => $node]);
    }

    /**
     * Обновление узла через сервисный токен (history-logger).
     * Используется для системных операций, например, подтверждения привязки зоны.
     */
    public function serviceUpdate(UpdateNodeRequest $request, DeviceNode $node)
    {
        $user = $this->authenticateUser($request);
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (! $request->attributes->get('service_auth')) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden',
            ], 403);
        }

        $data = $request->validated();
        $data = array_intersect_key($data, array_flip(['zone_id', 'pending_zone_id']));

        if (empty($data)) {
            return response()->json(['status' => 'ok', 'data' => $node]);
        }

        $node = $this->nodeService->update($node, $data);

        return response()->json(['status' => 'ok', 'data' => $node]);
    }

    /**
     * Аутентификация пользователя через Sanctum или сервисный токен.
     */
    private function authenticateUser(Request $request): ?\App\Models\User
    {
        $user = $request->user();

        // Если пользователь не авторизован через Sanctum, проверяем сервисный токен
        if (! $user) {
            $providedToken = $request->bearerToken();
            \Log::debug('[NodeController] Checking service token authentication');

            if ($providedToken) {
                $pyApiToken = config('services.python_bridge.token');
                $pyIngestToken = config('services.python_bridge.ingest_token');
                $historyLoggerToken = config('services.history_logger.token');

                $tokenValid = false;
                if ($pyApiToken && hash_equals($pyApiToken, $providedToken)) {
                    $tokenValid = true;
                } elseif ($pyIngestToken && hash_equals($pyIngestToken, $providedToken)) {
                    $tokenValid = true;
                } elseif ($historyLoggerToken && hash_equals($historyLoggerToken, $providedToken)) {
                    $tokenValid = true;
                }

                if ($tokenValid) {
                    $request->attributes->set('service_auth', true);
                    $serviceUser = \App\Models\User::where('role', 'operator')->first()
                        ?? \App\Models\User::where('role', 'admin')->first()
                        ?? \App\Models\User::first();

                    if ($serviceUser) {
                        $request->setUserResolver(static fn () => $serviceUser);

                        return $serviceUser;
                    }
                }
            }
        }

        return $user;
    }

    /**
     * Проверка изменения зоны узла.
     */
    private function validateZoneChange(\App\Models\User $user, DeviceNode $node, array $data): void
    {
        if (isset($data['zone_id']) && $data['zone_id'] !== $node->zone_id) {
            if (! \App\Helpers\ZoneAccessHelper::canAccessZone($user, $data['zone_id'])) {
                abort(403, 'Forbidden: Access denied to target zone');
            }
        }
    }

    /**
     * Отвязать узел от зоны.
     * При отвязке нода сбрасывается в REGISTERED_BACKEND и считается новой.
     */
    public function detach(Request $request, DeviceNode $node)
    {
        $this->authorize('detach', $node);

        try {
            $node = $this->nodeService->detach($node);

            return response()->json([
                'status' => 'ok',
                'data' => $node,
                'message' => 'Node detached from zone successfully',
            ]);
        } catch (\Exception $e) {
            \Illuminate\Support\Facades\Log::error('NodeController: Failed to detach node', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    public function destroy(Request $request, DeviceNode $node)
    {
        $this->authorize('delete', $node);

        try {
            $this->nodeService->delete($node);

            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            \Illuminate\Support\Facades\Log::warning('NodeController: Domain exception on node delete', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Exception $e) {
            \Illuminate\Support\Facades\Log::error('NodeController: Failed to delete node', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to delete node',
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Регистрация узла в системе.
     * Используется для регистрации новых узлов при первом подключении.
     * Требует токен аутентификации для защиты от несанкционированной регистрации.
     *
     * Безопасность: всегда требует токен, кроме случаев когда:
     * 1. Запрос идет с доверенного IP (настраивается через TRUSTED_PROXIES)
     * 2. И это node_hello от внутренних сервисов
     * 3. И только в dev режиме
     */
    public function register(\App\Http\Requests\RegisterNodeRequest $request)
    {
        // Проверка токена для защиты от несанкционированной регистрации
        // Используем PY_INGEST_TOKEN как основной токен для ingest операций
        $expectedToken = config('services.python_bridge.ingest_token') ?? config('services.python_bridge.token');
        $givenToken = $request->bearerToken();

        $clientIp = $request->ip();

        // Если токен настроен, он обязателен всегда
        if (! empty($expectedToken)) {
            if (empty($givenToken)) {
                \Illuminate\Support\Facades\Log::warning('Node registration: Missing token', [
                    'ip' => $clientIp,
                    'user_agent' => $request->userAgent(),
                ]);

                return response()->json([
                    'status' => 'error',
                    'message' => 'Unauthorized: token required',
                ], 401);
            }

            if (! hash_equals($expectedToken, (string) $givenToken)) {
                \Illuminate\Support\Facades\Log::warning('Node registration: Invalid token', [
                    'ip' => $clientIp,
                    'user_agent' => $request->userAgent(),
                ]);

                return response()->json([
                    'status' => 'error',
                    'message' => 'Unauthorized: invalid token',
                ], 401);
            }
        } else {
            // Если токен не настроен, всегда запрещаем регистрацию
            \Illuminate\Support\Facades\Log::error('Node registration: Token not configured', [
                'ip' => $clientIp,
                'env' => config('app.env'),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Node registration token not configured. Set PY_INGEST_TOKEN or PY_API_TOKEN.',
            ], 500);
        }

        $data = $request->validated();

        // Проверяем, это node_hello или обычная регистрация
        if ($request->has('message_type') && $request->input('message_type') === 'node_hello') {
            // Обработка node_hello из MQTT
            $node = $this->registryService->registerNodeFromHello($data);
        } else {
            // Обычная регистрация через API
            $node = $this->registryService->registerNode(
                $data['node_uid'],
                $data['zone_uid'] ?? null,
                $data
            );
        }

        return response()->json(['status' => 'ok', 'data' => $node], Response::HTTP_CREATED);
    }

    /**
     * Получить сохраненный NodeConfig для узла.
     * Для безопасности не включает Wi-Fi пароли и MQTT креды.
     */
    public function getConfig(Request $request, DeviceNode $node)
    {
        // Проверяем доступ к ноде
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (! \App\Helpers\ZoneAccessHelper::canAccessNode($user, $node)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this node',
            ], 403);
        }

        try {
            // Для API запросов не включаем креды (безопасность)
            $config = $this->configService->getStoredConfig($node, false);

            return response()->json(['status' => 'ok', 'data' => $config]);
        } catch (\InvalidArgumentException $e) {
            \Illuminate\Support\Facades\Log::warning('NodeController: Invalid argument on getConfig', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_BAD_REQUEST);
        } catch (\Exception $e) {
            \Illuminate\Support\Facades\Log::error('NodeController: Failed to get node config', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to get node config',
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Опубликовать NodeConfig через MQTT.
     * Конфиг больше не публикуется с сервера: ноды отправляют config_report на подключении.
     */
    public function publishConfig(PublishNodeConfigRequest $request, DeviceNode $node)
    {
        return response()->json([
            'status' => 'error',
            'message' => 'Config publishing from server is disabled. Nodes publish config_report on connect.',
        ], Response::HTTP_GONE);
    }

    /**
     * Заменить узел новым узлом.
     */
    public function swap(DeviceNode $node, Request $request)
    {
        $data = $request->validate([
            'new_hardware_id' => ['required', 'string', 'max:128'],
            'migrate_telemetry' => ['nullable', 'boolean'],
            'migrate_channels' => ['nullable', 'boolean'],
        ]);

        try {
            $newNode = $this->swapService->swapNode(
                $node->id,
                $data['new_hardware_id'],
                [
                    'migrate_telemetry' => $data['migrate_telemetry'] ?? false,
                    'migrate_channels' => $data['migrate_channels'] ?? true,
                ]
            );

            return response()->json([
                'status' => 'ok',
                'data' => $newNode,
            ]);
        } catch (\Exception $e) {
            \Illuminate\Support\Facades\Log::error('NodeController: Failed to swap node', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'new_hardware_id' => $data['new_hardware_id'] ?? null,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to swap node: '.$e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Переход узла в указанное lifecycle состояние.
     * POST /api/nodes/{node}/lifecycle/transition
     */
    public function transitionLifecycle(DeviceNode $node, Request $request)
    {
        $validated = $request->validate([
            'target_state' => ['required', 'string', 'in:'.implode(',', NodeLifecycleState::values())],
            'reason' => ['nullable', 'string', 'max:255'],
        ]);

        try {
            $targetState = NodeLifecycleState::from($validated['target_state']);
            $reason = $validated['reason'] ?? null;

            $success = $this->lifecycleService->transition($node, $targetState, $reason);

            if (! $success) {
                $currentState = $node->lifecycleState();

                return response()->json([
                    'status' => 'error',
                    'message' => "Transition from {$currentState->value} to {$targetState->value} is not allowed",
                    'current_state' => $currentState->value,
                    'target_state' => $targetState->value,
                ], Response::HTTP_BAD_REQUEST);
            }

            // Обновляем модель после перехода
            $node->refresh();

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'node' => $node->fresh(),
                    'previous_state' => $node->getOriginal('lifecycle_state'),
                    'current_state' => $node->lifecycle_state?->value,
                ],
            ]);
        } catch (\ValueError $e) {
            \Illuminate\Support\Facades\Log::warning('NodeController: Invalid lifecycle state', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'target_state' => $validated['target_state'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Invalid lifecycle state: '.$e->getMessage(),
            ], Response::HTTP_BAD_REQUEST);
        } catch (\Exception $e) {
            \Illuminate\Support\Facades\Log::error('NodeController: Failed to transition lifecycle', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'target_state' => $validated['target_state'] ?? null,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to transition lifecycle: '.$e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Получить разрешенные переходы для узла.
     * GET /api/nodes/{node}/lifecycle/allowed-transitions
     */
    public function getAllowedTransitions(DeviceNode $node)
    {
        try {
            $currentState = $node->lifecycleState();
            $allowedTransitions = [];

            // Получаем разрешенные переходы для текущего состояния
            foreach (NodeLifecycleState::cases() as $state) {
                if ($this->lifecycleService->isTransitionAllowed($currentState, $state)) {
                    $allowedTransitions[] = [
                        'value' => $state->value,
                        'label' => $state->label(),
                        'can_receive_telemetry' => $state->canReceiveTelemetry(),
                        'is_active' => $state->isActive(),
                    ];
                }
            }

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'current_state' => [
                        'value' => $currentState->value,
                        'label' => $currentState->label(),
                        'can_receive_telemetry' => $currentState->canReceiveTelemetry(),
                        'is_active' => $currentState->isActive(),
                    ],
                    'allowed_transitions' => $allowedTransitions,
                ],
            ]);
        } catch (\Exception $e) {
            \Illuminate\Support\Facades\Log::error('NodeController: Failed to get allowed transitions', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to get allowed transitions: '.$e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Проверяет, находится ли IP в указанном диапазоне (CIDR)
     */
    private function ipInRange(string $ip, string $range): bool
    {
        if (! str_contains($range, '/')) {
            return $ip === $range;
        }

        [$subnet, $mask] = explode('/', $range, 2);

        if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
            $ipLong = ip2long($ip);
            $subnetLong = ip2long($subnet);
            $maskLong = -1 << (32 - (int) $mask);

            return ($ipLong & $maskLong) === ($subnetLong & $maskLong);
        }

        if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) {
            $ipBin = inet_pton($ip);
            $subnetBin = inet_pton($subnet);

            if ($ipBin === false || $subnetBin === false) {
                return false;
            }

            $prefixLength = (int) $mask;
            if ($prefixLength < 0 || $prefixLength > 128) {
                return false;
            }

            // Применяем маску к обоим адресам
            $bytes = strlen($ipBin);
            $fullBytes = intval($prefixLength / 8);
            $remainingBits = $prefixLength % 8;

            // Сравниваем полные байты
            for ($i = 0; $i < $fullBytes; $i++) {
                if ($ipBin[$i] !== $subnetBin[$i]) {
                    return false;
                }
            }

            // Если есть оставшиеся биты, сравниваем их
            if ($remainingBits > 0 && $fullBytes < $bytes) {
                $maskByte = 0xFF << (8 - $remainingBits);
                $ipByte = ord($ipBin[$fullBytes]) & $maskByte;
                $subnetByte = ord($subnetBin[$fullBytes]) & $maskByte;

                if ($ipByte !== $subnetByte) {
                    return false;
                }
            }

            return true;
        }

        return false;
    }

    /**
     * Рекурсивно сортирует ключи массива для детерминированного JSON
     */
    private function recursiveKsort(array &$array): array
    {
        ksort($array);
        foreach ($array as &$value) {
            if (is_array($value)) {
                $this->recursiveKsort($value);
            }
        }
        return $array;
    }
}
