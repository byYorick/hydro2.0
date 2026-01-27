<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\ZoneSimulation;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class SimulationEventController extends Controller
{
    public function index(Request $request, ZoneSimulation $simulation): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (! ZoneAccessHelper::canAccessZone($user, $simulation->zone_id)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $validated = $request->validate([
            'limit' => ['nullable', 'integer', 'min:1', 'max:200'],
            'order' => ['nullable', 'string', 'in:asc,desc'],
            'service' => ['nullable', 'string', 'max:64'],
            'stage' => ['nullable', 'string', 'max:64'],
            'status' => ['nullable', 'string', 'max:32'],
            'level' => ['nullable', 'string', 'in:info,warning,error'],
            'after_id' => ['nullable', 'integer', 'min:0'],
            'since' => ['nullable', 'date'],
        ]);

        $limit = $validated['limit'] ?? 100;
        $order = $validated['order'] ?? 'asc';

        $query = $this->buildQuery($simulation->id, $validated);

        $events = $query
            ->orderBy('occurred_at', $order)
            ->orderBy('id', $order)
            ->limit($limit)
            ->get();

        $normalized = $events->map(fn ($event) => $this->normalizeEventRow($event))->values();
        $lastId = $normalized->last()['id'] ?? null;

        return response()->json([
            'status' => 'ok',
            'data' => $normalized,
            'meta' => [
                'limit' => $limit,
                'order' => $order,
                'last_id' => $lastId,
            ],
        ]);
    }

    public function stream(Request $request, ZoneSimulation $simulation)
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (! ZoneAccessHelper::canAccessZone($user, $simulation->zone_id)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $filters = $request->validate([
            'last_id' => ['nullable', 'integer', 'min:0'],
            'service' => ['nullable', 'string', 'max:64'],
            'stage' => ['nullable', 'string', 'max:64'],
            'status' => ['nullable', 'string', 'max:32'],
            'level' => ['nullable', 'string', 'in:info,warning,error'],
        ]);

        $maxExecutionTime = 1800;
        $startTime = time();
        $checkInterval = 2;

        return response()->stream(function () use ($simulation, $filters, $maxExecutionTime, $startTime, $checkInterval) {
            $lastId = (int) ($filters['last_id'] ?? 0);
            $iterations = 0;

            while (true) {
                if (time() - $startTime > $maxExecutionTime) {
                    Log::info('SimulationEventStream: Max execution time reached', [
                        'simulation_id' => $simulation->id,
                        'last_id' => $lastId,
                        'iterations' => $iterations,
                    ]);
                    echo "event: close\n";
                    echo "data: " . json_encode(['message' => 'Stream timeout']) . "\n\n";
                    @ob_flush();
                    @flush();
                    break;
                }

                if (connection_aborted()) {
                    Log::debug('SimulationEventStream: Client connection aborted', [
                        'simulation_id' => $simulation->id,
                        'last_id' => $lastId,
                        'iterations' => $iterations,
                    ]);
                    break;
                }

                if (memory_get_usage(true) > 128 * 1024 * 1024) {
                    Log::warning('SimulationEventStream: Memory limit reached', [
                        'simulation_id' => $simulation->id,
                        'last_id' => $lastId,
                        'iterations' => $iterations,
                        'memory' => memory_get_usage(true),
                    ]);
                    echo "event: error\n";
                    echo "data: " . json_encode(['message' => 'Server memory limit']) . "\n\n";
                    @ob_flush();
                    @flush();
                    break;
                }

                try {
                    $query = $this->buildQuery($simulation->id, $filters);
                    if ($lastId > 0) {
                        $query->where('id', '>', $lastId);
                    }

                    $items = $query
                        ->orderBy('id', 'asc')
                        ->limit(100)
                        ->get();

                    foreach ($items as $event) {
                        if (connection_aborted()) {
                            break 2;
                        }

                        $normalized = $this->normalizeEventRow($event);
                        $lastId = max($lastId, (int) $normalized['id']);

                        echo "event: simulation_event\n";
                        echo "data: " . json_encode($normalized, JSON_UNESCAPED_UNICODE) . "\n\n";
                        @ob_flush();
                        @flush();
                    }
                } catch (\Exception $e) {
                    Log::error('SimulationEventStream: Error during stream', [
                        'simulation_id' => $simulation->id,
                        'last_id' => $lastId,
                        'error' => $e->getMessage(),
                        'exception' => get_class($e),
                    ]);
                    echo "event: error\n";
                    echo "data: " . json_encode(['message' => 'Stream error occurred']) . "\n\n";
                    @ob_flush();
                    @flush();
                    break;
                }

                $iterations++;

                $sleepStart = time();
                while (time() - $sleepStart < $checkInterval) {
                    if (connection_aborted()) {
                        break 2;
                    }
                    usleep(100000);
                }
            }
        }, 200, [
            'Content-Type' => 'text/event-stream',
            'Cache-Control' => 'no-cache',
            'X-Accel-Buffering' => 'no',
            'Connection' => 'keep-alive',
        ]);
    }

    private function buildQuery(int $simulationId, array $filters)
    {
        $query = DB::table('simulation_events')
            ->where('simulation_id', $simulationId);

        if (! empty($filters['service'])) {
            $query->where('service', $filters['service']);
        }
        if (! empty($filters['stage'])) {
            $query->where('stage', $filters['stage']);
        }
        if (! empty($filters['status'])) {
            $query->where('status', $filters['status']);
        }
        if (! empty($filters['level'])) {
            $query->where('level', $filters['level']);
        }
        if (! empty($filters['after_id'])) {
            $query->where('id', '>', (int) $filters['after_id']);
        }
        if (! empty($filters['since'])) {
            $query->where('occurred_at', '>=', Carbon::parse($filters['since']));
        }

        return $query;
    }

    private function normalizeEventRow(object $event): array
    {
        $payload = $event->payload ?? null;
        if (is_string($payload)) {
            $decoded = json_decode($payload, true);
            $payload = json_last_error() === JSON_ERROR_NONE ? $decoded : $payload;
        }

        $occurredAt = $event->occurred_at ?? null;
        $createdAt = $event->created_at ?? null;

        return [
            'id' => $event->id,
            'simulation_id' => $event->simulation_id,
            'zone_id' => $event->zone_id,
            'service' => $event->service,
            'stage' => $event->stage,
            'status' => $event->status,
            'level' => $event->level,
            'message' => $event->message,
            'payload' => $payload,
            'occurred_at' => $occurredAt ? Carbon::parse($occurredAt)->toIso8601String() : null,
            'created_at' => $createdAt ? Carbon::parse($createdAt)->toIso8601String() : null,
        ];
    }
}
