<?php

namespace App\Http\Controllers;

use App\Models\GrowCycle;
use App\Models\User;
use App\Services\EffectiveTargetsService;
use App\Services\GrowCycleService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Validator;

/**
 * Internal API Controller для Python сервисов
 * Предоставляет batch endpoints для эффективной работы сервисов
 */
class InternalApiController extends Controller
{
    public function __construct(
        private EffectiveTargetsService $effectiveTargetsService,
        private GrowCycleService $growCycleService,
    ) {
    }

    /**
     * POST /api/internal/effective-targets/batch
     * Получить effective targets для нескольких зон одним запросом
     * 
     * Request body:
     * {
     *   "zone_ids": [1, 2, 3]
     * }
     * 
     * Response:
     * {
     *   "status": "ok",
     *   "data": {
     *     "1": {
     *       "cycle_id": 123,
     *       "zone_id": 1,
     *       "phase": {...},
     *       "targets": {...}
     *     },
     *     "2": {...},
     *     "3": null  // если нет активного цикла
     *   }
     * }
     */
    public function getEffectiveTargetsBatch(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'zone_ids' => ['required', 'array', 'min:1', 'max:100'],
            'zone_ids.*' => ['required', 'integer', 'exists:zones,id'],
        ]);

        if ($validator->fails()) {
            return response()->json([
                'status' => 'error',
                'message' => 'Validation failed',
                'errors' => $validator->errors(),
            ], 422);
        }

        $zoneIds = $request->input('zone_ids', []);

        try {
            // Получаем активные циклы для зон
            $cycles = \App\Models\GrowCycle::query()
                ->whereIn('zone_id', $zoneIds)
                ->whereIn('status', [
                    \App\Enums\GrowCycleStatus::PLANNED,
                    \App\Enums\GrowCycleStatus::RUNNING,
                    \App\Enums\GrowCycleStatus::PAUSED,
                ])
                ->get()
                ->keyBy('zone_id');

            $results = [];

            foreach ($zoneIds as $zoneId) {
                $cycle = $cycles->get($zoneId);
                
                if (!$cycle) {
                    $results[$zoneId] = null;
                    continue;
                }

                try {
                    $effectiveTargets = $this->effectiveTargetsService->getEffectiveTargets($cycle->id);
                    $results[$zoneId] = $effectiveTargets;
                } catch (\Exception $e) {
                    Log::warning('Failed to get effective targets for cycle', [
                        'zone_id' => $zoneId,
                        'cycle_id' => $cycle->id,
                        'error' => $e->getMessage(),
                    ]);
                    $results[$zoneId] = [
                        'error' => $e->getMessage(),
                    ];
                }
            }

            return response()->json([
                'status' => 'ok',
                'data' => $results,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to get effective targets batch', [
                'zone_ids' => $zoneIds,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to get effective targets',
                'error' => $e->getMessage(),
            ], 500);
        }
    }

    /**
     * POST /api/internal/grow-cycles/{growCycle}/advance-phase
     */
    public function advanceGrowCyclePhase(GrowCycle $growCycle): JsonResponse
    {
        try {
            $userId = $this->resolveSystemUserId();
            $cycle = $this->growCycleService->advancePhase($growCycle, $userId);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], 422);
        } catch (\Exception $e) {
            Log::error('Internal advance phase failed', [
                'cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], 500);
        }
    }

    /**
     * POST /api/internal/grow-cycles/{growCycle}/harvest
     */
    public function harvestGrowCycle(GrowCycle $growCycle): JsonResponse
    {
        try {
            $userId = $this->resolveSystemUserId();
            $cycle = $this->growCycleService->harvest($growCycle, [
                'batch_label' => 'SIM',
            ], $userId);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], 422);
        } catch (\Exception $e) {
            Log::error('Internal harvest failed', [
                'cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], 500);
        }
    }

    private function resolveSystemUserId(): int
    {
        $userId = User::query()->orderBy('id')->value('id');
        if (! $userId) {
            throw new \RuntimeException('No users available for internal action.');
        }

        return (int) $userId;
    }
}
