<?php

namespace App\Http\Controllers;

use App\Models\SystemLog;
use Carbon\Carbon;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ServiceLogController extends Controller
{
    /**
     * Вернуть логи сервисов с фильтрами и пагинацией.
     */
    public function index(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'service' => ['nullable', 'string', 'max:64'],
            'level' => ['nullable', 'string', 'max:32'],
            'search' => ['nullable', 'string', 'max:255'],
            'from' => ['nullable', 'date'],
            'to' => ['nullable', 'date'],
            'page' => ['nullable', 'integer', 'min:1'],
            'per_page' => ['nullable', 'integer', 'min:1', 'max:200'],
        ]);

        $service = $validated['service'] ?? null;
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
            ->when($level, fn ($q) => $q->whereRaw('UPPER(level) = ?', [strtoupper($level)]))
            ->when($search, function ($q) use ($search) {
                $like = '%'.$search.'%';
                $q->where(function ($sub) use ($like) {
                    $sub->where('message', 'ILIKE', $like)
                        ->orWhereRaw("context::text ILIKE ?", [$like]);
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
        $validated = $request->validate([
            'service' => ['required', 'string', 'max:64'],
            'level' => ['required', 'string', 'max:32'],
            'message' => ['required', 'string', 'max:2000'],
            'context' => ['nullable', 'array'],
            'created_at' => ['nullable', 'date'],
            'timestamp' => ['nullable', 'integer'], // timestamp в миллисекундах
        ]);

        $context = $validated['context'] ?? [];
        // Гарантируем, что service сохранится в контексте для фильтров
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

        return response()->json([
            'status' => 'ok',
            'data' => [
                'id' => $log->id,
            ],
        ]);
    }
}
