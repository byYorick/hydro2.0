<?php

namespace App\Http\Controllers;

use App\Models\SystemLog;
use Carbon\Carbon;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\ValidationException;

class ServiceLogController extends Controller
{
    /**
     * Вернуть логи сервисов с фильтрами и пагинацией.
     */
    public function index(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'service' => ['nullable', 'string', 'max:64'],
            'exclude_services' => ['nullable', 'array'],
            'exclude_services.*' => ['string', 'max:64'],
            'level' => ['nullable', 'string', 'max:32'],
            'search' => ['nullable', 'string', 'max:255'],
            'from' => ['nullable', 'date'],
            'to' => ['nullable', 'date'],
            'page' => ['nullable', 'integer', 'min:1'],
            'per_page' => ['nullable', 'integer', 'min:1', 'max:200'],
        ]);

        $service = $validated['service'] ?? null;
        $excludeServices = $validated['exclude_services'] ?? [];
        $level = $validated['level'] ?? null;
        $search = $validated['search'] ?? null;
        $from = $validated['from'] ?? null;
        $to = $validated['to'] ?? null;
        $page = (int) ($validated['page'] ?? 1);
        $perPage = (int) ($validated['per_page'] ?? 50);

        $query = SystemLog::query()
            ->select(['id', 'level', 'message', 'context', 'created_at'])
            ->when(
                $service,
                fn ($q) => $q->whereRaw("coalesce(context->>'service', context->>'source', 'system') = ?", [$service])
            )
            ->when(! empty($excludeServices), function ($q) use ($excludeServices) {
                $placeholders = implode(',', array_fill(0, count($excludeServices), '?'));
                $q->whereRaw(
                    "coalesce(context->>'service', context->>'source', 'system') not in ({$placeholders})",
                    $excludeServices
                );
            })
            ->when($level, fn ($q) => $q->whereRaw('UPPER(level) = ?', [strtoupper($level)]))
            ->when($search, function ($q) use ($search) {
                $like = '%'.$search.'%';
                $q->where(function ($sub) use ($like) {
                    $sub->where('message', 'ILIKE', $like)
                        ->orWhereRaw('context::text ILIKE ?', [$like]);
                });
            })
            ->when($from, fn ($q) => $q->where('created_at', '>=', $from))
            ->when($to, fn ($q) => $q->where('created_at', '<=', $to))
            ->orderBy('created_at', 'desc');

        $logs = $query->paginate($perPage, ['*'], 'page', $page);

        $data = collect($logs->items())->map(function (SystemLog $log) {
            return [
                'id' => $log->id,
                'service' => $log->service,
                'level' => strtoupper($log->level ?? 'INFO'),
                'message' => $log->message,
                'context' => $log->context ?? [],
                'created_at' => $log->created_at?->toIso8601String(),
            ];
        });

        return response()->json([
            'status' => 'ok',
            'data' => $data,
            'meta' => [
                'page' => $logs->currentPage(),
                'per_page' => $logs->perPage(),
                'total' => $logs->total(),
                'last_page' => $logs->lastPage(),
            ],
        ]);
    }

    /**
     * Приём логов от внутренних сервисов (Python и Laravel cron).
     */
    public function store(Request $request): JsonResponse
    {
        $structuredPayload = $this->resolveStructuredPayload($request);
        if ($structuredPayload !== null) {
            $log = $this->storeStructuredPayload($structuredPayload);
        } else {
            $validated = $request->validate([
                'service' => ['required', 'string', 'max:64'],
                'level' => ['required', 'string', 'max:32'],
                'message' => ['required', 'string', 'max:2000'],
                'context' => ['nullable', 'array'],
                'created_at' => ['nullable', 'date'],
                'timestamp' => ['nullable', 'integer'], // timestamp в миллисекундах
            ]);

            $context = $validated['context'] ?? [];
            $context['service'] = $validated['service'];

            $timestamp = $validated['created_at'] ?? null;
            if ($timestamp && is_string($timestamp)) {
                $timestamp = Carbon::parse($timestamp);
            }
            if (! $timestamp && isset($validated['timestamp'])) {
                $timestamp = Carbon::createFromTimestampMs((int) $validated['timestamp']);
            }

            $log = SystemLog::create([
                'level' => strtolower($validated['level']),
                'message' => $validated['message'],
                'context' => $context,
                'created_at' => $timestamp ?: now(),
            ]);
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'id' => $log->id,
            ],
        ]);
    }

    /**
     * Извлечь структурированный payload (JSON) если он был передан.
     *
     * @return array<string, mixed>|null
     *
     * @throws ValidationException
     */
    private function resolveStructuredPayload(Request $request): ?array
    {
        $payload = $request->input('log');
        if ($payload === null && $request->has('payload')) {
            $payload = $request->input('payload');
        }

        if ($payload === null && ($request->has('logger') || $request->has('exception') || $request->has('trace_id'))) {
            $payload = $request->all();
        }

        if ($payload === null) {
            return null;
        }

        if (is_string($payload)) {
            $decoded = json_decode($payload, true);
            if (! is_array($decoded)) {
                throw ValidationException::withMessages([
                    'log' => ['Invalid JSON payload.'],
                ]);
            }

            return $decoded;
        }

        if (! is_array($payload)) {
            throw ValidationException::withMessages([
                'log' => ['Log payload must be an object or JSON string.'],
            ]);
        }

        return $payload;
    }

    /**
     * Сохранить структурированный payload в system_logs.
     *
     * @param array<string, mixed> $payload
     */
    private function storeStructuredPayload(array $payload): SystemLog
    {
        $level = $payload['level'] ?? null;
        $message = $payload['message'] ?? null;
        if (! is_string($level) || ! is_string($message)) {
            throw ValidationException::withMessages([
                'log' => ['Structured log must include string level and message.'],
            ]);
        }

        $service = 'system';
        if (isset($payload['service']) && is_string($payload['service'])) {
            $service = $payload['service'];
        } elseif (isset($payload['context']) && is_array($payload['context']) && isset($payload['context']['service'])) {
            $service = (string) $payload['context']['service'];
        } elseif (isset($payload['source']) && is_string($payload['source'])) {
            $service = $payload['source'];
        }

        $timestamp = $payload['timestamp'] ?? $payload['created_at'] ?? null;
        $createdAt = $this->parseTimestamp($timestamp);

        $context = $payload;
        unset($context['level'], $context['message'], $context['timestamp'], $context['created_at']);
        $context['service'] = $service;

        return SystemLog::create([
            'level' => strtolower($level),
            'message' => $message,
            'context' => $context,
            'created_at' => $createdAt ?: now(),
        ]);
    }

    private function parseTimestamp(mixed $timestamp): ?Carbon
    {
        if ($timestamp instanceof Carbon) {
            return $timestamp;
        }

        if (is_string($timestamp)) {
            return Carbon::parse($timestamp);
        }

        if (is_int($timestamp) || is_float($timestamp)) {
            $value = (int) $timestamp;
            if ($value > 9999999999) {
                return Carbon::createFromTimestampMs($value);
            }

            return Carbon::createFromTimestamp($value);
        }

        if (is_numeric($timestamp)) {
            $value = (int) $timestamp;
            if ($value > 9999999999) {
                return Carbon::createFromTimestampMs($value);
            }

            return Carbon::createFromTimestamp($value);
        }

        return null;
    }
}
