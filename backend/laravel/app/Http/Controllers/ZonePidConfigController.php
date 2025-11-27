<?php

namespace App\Http\Controllers;

use App\Http\Requests\UpdateZonePidConfigRequest;
use App\Models\Zone;
use App\Services\ZonePidConfigService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Auth;

class ZonePidConfigController extends Controller
{
    public function __construct(
        private ZonePidConfigService $pidConfigService
    ) {}

    /**
     * Получить все PID конфиги для зоны
     */
    public function index(Zone $zone): JsonResponse
    {
        $configs = $this->pidConfigService->getAllConfigs($zone->id);

        // Если конфигов нет, возвращаем дефолтные
        $result = [];
        foreach (['ph', 'ec'] as $type) {
            if (isset($configs[$type])) {
                $result[$type] = $configs[$type];
            } else {
                $result[$type] = [
                    'type' => $type,
                    'config' => $this->pidConfigService->getDefaultConfig($type),
                    'is_default' => true,
                ];
            }
        }

        return response()->json([
            'status' => 'ok',
            'data' => $result,
        ]);
    }

    /**
     * Получить PID конфиг для зоны и типа
     */
    public function show(Zone $zone, string $type): JsonResponse
    {
        // Валидация типа
        if (! in_array($type, ['ph', 'ec'])) {
            return response()->json([
                'status' => 'error',
                'message' => 'Invalid type. Must be "ph" or "ec".',
            ], Response::HTTP_BAD_REQUEST);
        }

        $config = $this->pidConfigService->getConfig($zone->id, $type);

        if (! $config) {
            // Возвращаем дефолтный конфиг
            return response()->json([
                'status' => 'ok',
                'data' => [
                    'type' => $type,
                    'config' => $this->pidConfigService->getDefaultConfig($type),
                    'is_default' => true,
                ],
            ]);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $config,
        ]);
    }

    /**
     * Создать или обновить PID конфиг
     */
    public function update(UpdateZonePidConfigRequest $request, Zone $zone, string $type): JsonResponse
    {
        // Валидация типа
        if (! in_array($type, ['ph', 'ec'])) {
            return response()->json([
                'status' => 'error',
                'message' => 'Invalid type. Must be "ph" or "ec".',
            ], Response::HTTP_BAD_REQUEST);
        }

        $validated = $request->validated();
        $config = $validated['config'];
        $userId = Auth::id();

        try {
            // Дополнительная валидация
            $this->pidConfigService->validateConfig($config, $type);

            $pidConfig = $this->pidConfigService->createOrUpdate(
                $zone->id,
                $type,
                $config,
                $userId
            );

            return response()->json([
                'status' => 'ok',
                'data' => $pidConfig,
            ]);
        } catch (\InvalidArgumentException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }
}
