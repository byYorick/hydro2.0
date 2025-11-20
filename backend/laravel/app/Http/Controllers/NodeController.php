<?php

namespace App\Http\Controllers;

use App\Models\DeviceNode;
use App\Services\NodeService;
use App\Services\NodeRegistryService;
use App\Services\NodeConfigService;
use App\Services\NodeSwapService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class NodeController extends Controller
{
    public function __construct(
        private NodeService $nodeService,
        private NodeRegistryService $registryService,
        private NodeConfigService $configService,
        private NodeSwapService $swapService
    ) {
    }

    public function index(Request $request)
    {
        // Eager loading для предотвращения N+1 запросов
        $query = DeviceNode::query()
            ->with(['zone:id,name,status', 'channels']); // Загружаем связанные данные
        
        if ($request->filled('zone_id')) {
            $query->where('zone_id', $request->integer('zone_id'));
        }
        if ($request->filled('status')) {
            $query->where('status', $request->string('status'));
        }
        // Поиск новых нод (без привязки к зоне)
        if ($request->boolean('new_only')) {
            $query->whereNull('zone_id');
        }
        // Поиск непривязанных нод (новые или без зоны)
        if ($request->boolean('unassigned')) {
            $query->whereNull('zone_id');
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

    public function destroy(DeviceNode $node)
    {
        try {
            $this->nodeService->delete($node);
            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    /**
     * Регистрация узла в системе.
     * Используется для регистрации новых узлов при первом подключении.
     * Требует токен аутентификации для защиты от несанкционированной регистрации.
     */
    public function register(Request $request)
    {
        // Проверка токена для защиты от несанкционированной регистрации
        $expectedToken = config('services.python_bridge.ingest_token') ?? config('services.python_bridge.token');
        $givenToken = $request->bearerToken();
        
        // Если токен настроен, он обязателен
        if ($expectedToken && !hash_equals($expectedToken, (string)$givenToken)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: token required',
            ], 401);
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
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_BAD_REQUEST);
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
            
            $response = \Illuminate\Support\Facades\Http::withHeaders($headers)
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
            
            return response()->json([
                'status' => 'error',
                'message' => 'Failed to publish config via MQTT bridge',
                'details' => $response->json(),
            ], $response->status());
        } catch (\InvalidArgumentException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_BAD_REQUEST);
        } catch (\Exception $e) {
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
            return response()->json([
                'status' => 'error',
                'message' => 'Failed to swap node: ' . $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }
}


