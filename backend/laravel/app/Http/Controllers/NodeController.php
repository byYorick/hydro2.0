<?php

namespace App\Http\Controllers;

use App\Models\DeviceNode;
use App\Services\NodeService;
use App\Services\NodeRegistryService;
use App\Services\NodeConfigService;
use App\Services\NodeSwapService;
use App\Services\NodeLifecycleService;
use App\Enums\NodeLifecycleState;
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
    ) {
    }

    public function index(Request $request)
    {
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
        
        // Eager loading для предотвращения N+1 запросов
        $query = DeviceNode::query()
            ->with(['zone:id,name,status', 'channels']); // Загружаем связанные данные
        
        if (isset($validated['zone_id'])) {
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
            $searchTerm = '%' . strtolower($validated['search']) . '%';
            $query->where(function ($q) use ($searchTerm) {
                $q->whereRaw('LOWER(name) LIKE ?', [$searchTerm])
                  ->orWhereRaw('LOWER(uid) LIKE ?', [$searchTerm])
                  ->orWhereRaw('LOWER(type) LIKE ?', [$searchTerm]);
            });
        }
        
        $items = $query->latest('id')->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'zone_id' => ['nullable', 'integer', 'exists:zones,id'],
            'uid' => ['required', 'string', 'max:64', 'unique:nodes,uid'],
            'name' => ['nullable', 'string', 'max:255'],
            'type' => ['nullable', 'string', 'max:64'],
            'fw_version' => ['nullable', 'string', 'max:64'],
            'status' => ['nullable', 'string', 'max:32'],
            'config' => ['nullable', 'array'],
        ]);
        $node = $this->nodeService->create($data);
        return response()->json(['status' => 'ok', 'data' => $node], Response::HTTP_CREATED);
    }

    public function show(DeviceNode $node)
    {
        $node->load('channels');
        return response()->json(['status' => 'ok', 'data' => $node]);
    }

    public function update(Request $request, DeviceNode $node)
    {
        $data = $request->validate([
            'zone_id' => ['nullable', 'integer', 'exists:zones,id'],
            'uid' => ['sometimes', 'string', 'max:64', 'unique:nodes,uid,'.$node->id],
            'name' => ['nullable', 'string', 'max:255'],
            'type' => ['nullable', 'string', 'max:64'],
            'fw_version' => ['nullable', 'string', 'max:64'],
            'status' => ['nullable', 'string', 'max:32'],
            'config' => ['nullable', 'array'],
        ]);
        $node = $this->nodeService->update($node, $data);
        return response()->json(['status' => 'ok', 'data' => $node]);
    }

    /**
     * Отвязать узел от зоны.
     * При отвязке нода сбрасывается в REGISTERED_BACKEND и считается новой.
     */
    public function detach(DeviceNode $node)
    {
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

    public function destroy(DeviceNode $node)
    {
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
    public function register(Request $request)
    {
        // Проверка токена для защиты от несанкционированной регистрации
        $expectedToken = config('services.python_bridge.ingest_token') ?? config('services.python_bridge.token');
        $givenToken = $request->bearerToken();
        
        $clientIp = $request->ip();
        $isNodeHello = $request->has('message_type') && $request->input('message_type') === 'node_hello';
        
        // Проверяем, является ли IP доверенным (только если настроены доверенные прокси)
        $trustedProxies = config('trustedproxy.proxies', []);
        $isTrustedIp = false;
        
        // Проверяем, находится ли IP в списке доверенных
        // В production всегда требуем токен, если он настроен
        if (!empty($trustedProxies)) {
            foreach ($trustedProxies as $trustedProxy) {
                if ($clientIp === $trustedProxy || 
                    (str_contains($trustedProxy, '/') && $this->ipInRange($clientIp, $trustedProxy))) {
                    $isTrustedIp = true;
                    break;
                }
            }
        }
        
        // Проверяем внутренние IP только если это dev режим и IP действительно внутренний
        $isInternalIp = false;
        if (config('app.env') === 'local' || config('app.debug')) {
            $isInternalIp = in_array($clientIp, ['127.0.0.1', '::1']) || 
                           str_starts_with($clientIp, '172.') ||
                           str_starts_with($clientIp, '10.') ||
                           str_starts_with($clientIp, '192.168.');
        }
        
        // Если токен настроен, он обязателен, кроме специальных случаев
        if (!empty($expectedToken)) {
            $allowWithoutToken = false;
            
            // Разрешаем без токена только если:
            // 1. Это node_hello от внутренних сервисов
            // 2. И IP доверенный или внутренний
            // 3. И только в dev режиме
            if ($isNodeHello && ($isTrustedIp || $isInternalIp) && 
                (config('app.env') === 'local' || config('app.debug'))) {
                \Illuminate\Support\Facades\Log::info('Node registration: Allowing node_hello without token from trusted IP', [
                    'ip' => $clientIp,
                    'is_trusted' => $isTrustedIp,
                    'is_internal' => $isInternalIp,
                ]);
                $allowWithoutToken = true;
            }
            
            if (!$allowWithoutToken) {
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
                
                if (!hash_equals($expectedToken, (string)$givenToken)) {
                    \Illuminate\Support\Facades\Log::warning('Node registration: Invalid token', [
                        'ip' => $clientIp,
                        'user_agent' => $request->userAgent(),
                    ]);
                    return response()->json([
                        'status' => 'error',
                        'message' => 'Unauthorized: invalid token',
                    ], 401);
                }
            }
        } else {
            // Если токен не настроен, логируем предупреждение
            \Illuminate\Support\Facades\Log::warning('Node registration: Token not configured', [
                'ip' => $clientIp,
                'env' => config('app.env'),
            ]);
            
            // В production без токена запрещаем регистрацию
            if (config('app.env') !== 'local' && !config('app.debug')) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Node registration token not configured',
                ], 500);
            }
        }
        
        // Проверяем, это node_hello или обычная регистрация
        if ($request->has('message_type') && $request->input('message_type') === 'node_hello') {
            // Обработка node_hello из MQTT
            $data = $request->validate([
                'message_type' => ['required', 'string', 'in:node_hello'],
                'hardware_id' => ['required', 'string', 'max:128'],
                'node_type' => ['nullable', 'string', 'max:64'],
                'fw_version' => ['nullable', 'string', 'max:64'],
                'hardware_revision' => ['nullable', 'string', 'max:64'],
                'capabilities' => ['nullable', 'array'],
                'provisioning_meta' => ['nullable', 'array'],
            ]);
            
            $node = $this->registryService->registerNodeFromHello($data);
        } else {
            // Обычная регистрация через API
            $data = $request->validate([
                'node_uid' => ['required', 'string', 'max:64'],
                'zone_uid' => ['nullable', 'string', 'max:64'],
                'firmware_version' => ['nullable', 'string', 'max:64'],
                'hardware_revision' => ['nullable', 'string', 'max:64'],
                'hardware_id' => ['nullable', 'string', 'max:128'],
                'name' => ['nullable', 'string', 'max:255'],
                'type' => ['nullable', 'string', 'max:64'],
            ]);
            
            $node = $this->registryService->registerNode(
                $data['node_uid'],
                $data['zone_uid'] ?? null,
                $data
            );
        }
        
        return response()->json(['status' => 'ok', 'data' => $node], Response::HTTP_CREATED);
    }

    /**
     * Получить NodeConfig для узла.
     */
    public function getConfig(DeviceNode $node)
    {
        try {
            $config = $this->configService->generateNodeConfig($node);
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
     * Это проксирует запрос в mqtt-bridge для публикации конфига.
     */
    public function publishConfig(DeviceNode $node, Request $request)
    {
        try {
            $config = $this->configService->generateNodeConfig($node);
            
            // Проверяем, что узел привязан к зоне
            if (!$node->zone_id) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Node must be assigned to a zone before publishing config',
                ], Response::HTTP_BAD_REQUEST);
            }
            
            // Получаем greenhouse_uid
            $node->load('zone.greenhouse');
            $greenhouseUid = $node->zone?->greenhouse?->uid;
            if (!$greenhouseUid) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Zone must have a greenhouse before publishing config',
                ], Response::HTTP_BAD_REQUEST);
            }
            
            // Вызываем mqtt-bridge API для публикации
            $baseUrl = config('services.python_bridge.base_url');
            $token = config('services.python_bridge.token');
            
            if (!$baseUrl) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'MQTT bridge URL not configured',
                ], Response::HTTP_INTERNAL_SERVER_ERROR);
            }
            
            $headers = [];
            if ($token) {
                $headers['Authorization'] = "Bearer {$token}";
            }
            
            // Используем короткий таймаут, чтобы не блокировать workers
            $timeout = 10; // секунд
            
            try {
                $response = \Illuminate\Support\Facades\Http::withHeaders($headers)
                    ->timeout($timeout)
                    ->post("{$baseUrl}/bridge/nodes/{$node->uid}/config", [
                        'node_uid' => $node->uid,
                        'zone_id' => $node->zone_id,
                        'greenhouse_uid' => $greenhouseUid,
                        'config' => $config,
                    ]);
                
                if ($response->successful()) {
                    return response()->json([
                        'status' => 'ok',
                        'data' => $response->json('data'),
                    ]);
                }
                
                \Illuminate\Support\Facades\Log::warning('NodeController: Failed to publish config - non-successful response', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'status' => $response->status(),
                    'response_preview' => substr($response->body(), 0, 500),
                ]);
                
                return response()->json([
                    'status' => 'error',
                    'message' => 'Failed to publish config via MQTT bridge',
                    'details' => $response->json(),
                ], $response->status());
            } catch (\Illuminate\Http\Client\ConnectionException $e) {
                \Illuminate\Support\Facades\Log::error('NodeController: Connection error on publishConfig', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'error' => $e->getMessage(),
                ]);
                return response()->json([
                    'status' => 'error',
                    'code' => 'SERVICE_UNAVAILABLE',
                    'message' => 'MQTT bridge service is currently unavailable. Please try again later.',
                ], 503);
            } catch (\Illuminate\Http\Client\TimeoutException $e) {
                \Illuminate\Support\Facades\Log::error('NodeController: Timeout error on publishConfig', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'timeout' => $timeout,
                ]);
                return response()->json([
                    'status' => 'error',
                    'code' => 'SERVICE_TIMEOUT',
                    'message' => 'MQTT bridge service did not respond in time. Please try again later.',
                ], 503);
            } catch (\Illuminate\Http\Client\RequestException $e) {
                \Illuminate\Support\Facades\Log::error('NodeController: Request error on publishConfig', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'error' => $e->getMessage(),
                    'status' => $e->response?->status(),
                ]);
                return response()->json([
                    'status' => 'error',
                    'code' => 'PUBLISH_FAILED',
                    'message' => 'Failed to publish config via MQTT bridge',
                ], 500);
            }
        } catch (\InvalidArgumentException $e) {
            \Illuminate\Support\Facades\Log::warning('NodeController: Invalid argument on publishConfig', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'error' => $e->getMessage(),
            ]);
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_BAD_REQUEST);
        } catch (\Exception $e) {
            \Illuminate\Support\Facades\Log::error('NodeController: Failed to publish config', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);
            return response()->json([
                'status' => 'error',
                'message' => 'Failed to publish config: ' . $e->getMessage(),
                ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
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
                'message' => 'Failed to swap node: ' . $e->getMessage(),
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
            'target_state' => ['required', 'string', 'in:' . implode(',', NodeLifecycleState::values())],
            'reason' => ['nullable', 'string', 'max:255'],
        ]);

        try {
            $targetState = NodeLifecycleState::from($validated['target_state']);
            $reason = $validated['reason'] ?? null;

            $success = $this->lifecycleService->transition($node, $targetState, $reason);

            if (!$success) {
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
                'message' => 'Invalid lifecycle state: ' . $e->getMessage(),
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
                'message' => 'Failed to transition lifecycle: ' . $e->getMessage(),
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
                'message' => 'Failed to get allowed transitions: ' . $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Проверяет, находится ли IP в указанном диапазоне (CIDR)
     */
    private function ipInRange(string $ip, string $range): bool
    {
        if (!str_contains($range, '/')) {
            return $ip === $range;
        }

        [$subnet, $mask] = explode('/', $range, 2);
        
        if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
            $ipLong = ip2long($ip);
            $subnetLong = ip2long($subnet);
            $maskLong = -1 << (32 - (int)$mask);
            return ($ipLong & $maskLong) === ($subnetLong & $maskLong);
        }

        if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) {
            // Упрощенная проверка для IPv6
            return inet_pton($ip) && inet_pton($subnet);
        }

        return false;
    }
}


