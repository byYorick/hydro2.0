<?php

namespace App\Http\Controllers;

use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Helpers\ZoneAccessHelper;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;

class TelemetryController extends Controller
{
    public function zoneLast(int $zoneId)
    {
        // Проверяем авторизацию
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone(Auth::user(), $zoneId)) {
            Log::warning('TelemetryController: Unauthorized access attempt to zone telemetry', [
                'user_id' => Auth::id(),
                'zone_id' => $zoneId,
            ]);
            
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN',
                'message' => 'Access denied',
            ], 403);
        }
        
        $rows = TelemetryLast::query()
            ->where('zone_id', $zoneId)
            ->get();

        return response()->json([
            'status' => 'ok',
            'data' => $rows,
        ]);
    }

    public function zoneHistory(Request $request, int $zoneId)
    {
        // Проверяем авторизацию
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone(Auth::user(), $zoneId)) {
            Log::warning('TelemetryController: Unauthorized access attempt to zone history', [
                'user_id' => Auth::id(),
                'zone_id' => $zoneId,
            ]);
            
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN',
                'message' => 'Access denied',
            ], 403);
        }
        
        $validated = $request->validate([
            'metric' => ['required', 'string', 'max:64'],
            'from' => ['nullable', 'date'],
            'to' => ['nullable', 'date'],
        ]);

        $q = TelemetrySample::query()->where('zone_id', $zoneId)
            ->where('metric_type', $validated['metric'])
            ->orderBy('ts', 'asc');

        if (!empty($validated['from'])) {
            $q->where('ts', '>=', $validated['from']);
        }
        if (!empty($validated['to'])) {
            $q->where('ts', '<=', $validated['to']);
        }

        $rows = $q->limit(5000)->get(['ts', 'value', 'node_id', 'channel']);

        return response()->json([
            'status' => 'ok',
            'data' => $rows,
        ]);
    }

    public function nodeLast(int $nodeId)
    {
        // Проверяем авторизацию
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }
        
        // Проверяем доступ к ноде
        if (!ZoneAccessHelper::canAccessNode(Auth::user(), $nodeId)) {
            Log::warning('TelemetryController: Unauthorized access attempt to node telemetry', [
                'user_id' => Auth::id(),
                'node_id' => $nodeId,
            ]);
            
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN',
                'message' => 'Access denied',
            ], 403);
        }
        
        $rows = TelemetryLast::query()
            ->where('node_id', $nodeId)
            ->get();

        return response()->json([
            'status' => 'ok',
            'data' => $rows,
        ]);
    }

    /**
     * Получить историю телеметрии для конкретной ноды
     */
    public function nodeHistory(Request $request, int $nodeId)
    {
        // Проверяем авторизацию
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }
        
        // Проверяем доступ к ноде
        if (!ZoneAccessHelper::canAccessNode(Auth::user(), $nodeId)) {
            Log::warning('TelemetryController: Unauthorized access attempt to node history', [
                'user_id' => Auth::id(),
                'node_id' => $nodeId,
            ]);
            
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN',
                'message' => 'Access denied',
            ], 403);
        }
        
        $validated = $request->validate([
            'metric' => ['required', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:64'],
            'from' => ['nullable', 'date'],
            'to' => ['nullable', 'date'],
        ]);

        $q = TelemetrySample::query()->where('node_id', $nodeId)
            ->where('metric_type', $validated['metric'])
            ->orderBy('ts', 'asc');

        if (!empty($validated['channel'])) {
            $q->where('channel', $validated['channel']);
        }

        if (!empty($validated['from'])) {
            $q->where('ts', '>=', $validated['from']);
        }
        if (!empty($validated['to'])) {
            $q->where('ts', '<=', $validated['to']);
        }

        $rows = $q->limit(5000)->get(['ts', 'value', 'channel']);

        return response()->json([
            'status' => 'ok',
            'data' => $rows,
        ]);
    }

    /**
     * Получить агрегированные данные телеметрии
     * 
     * @param Request $request
     * @return \Illuminate\Http\JsonResponse
     */
    public function aggregates(Request $request)
    {
        // Проверяем авторизацию
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }
        
        $validated = $request->validate([
            'zone_id' => ['required', 'integer', 'exists:zones,id'],
            'metric' => ['required', 'string'],
            'period' => ['required', 'string', 'in:1h,24h,7d,30d'],
        ]);

        $zoneId = $validated['zone_id'];
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone(Auth::user(), $zoneId)) {
            Log::warning('TelemetryController: Unauthorized access attempt to zone aggregates', [
                'user_id' => Auth::id(),
                'zone_id' => $zoneId,
            ]);
            
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN',
                'message' => 'Access denied',
            ], 403);
        }
        $metric = strtoupper($validated['metric']); // Преобразуем в верхний регистр (ph -> PH)
        $period = $validated['period'];

        // Валидация метрики после преобразования
        $allowedMetrics = ['PH', 'EC', 'TEMP', 'HUMIDITY', 'WATER_LEVEL', 'FLOW_RATE'];
        if (!in_array($metric, $allowedMetrics)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Invalid metric. Allowed: ' . implode(', ', array_map('strtolower', $allowedMetrics)),
            ], 400);
        }

        // Определяем временной диапазон
        $now = now();
        $from = match($period) {
            '1h' => $now->copy()->subHour(),
            '24h' => $now->copy()->subDay(),
            '7d' => $now->copy()->subWeek(),
            '30d' => $now->copy()->subMonth(),
            default => $now->copy()->subDay(),
        };

        // Определяем таблицу агрегации и интервал в зависимости от периода
        $table = match($period) {
            '1h' => 'telemetry_agg_1m', // Для 1 часа используем минутные агрегаты
            '24h' => 'telemetry_agg_1h', // Для 24 часов используем часовые агрегаты
            '7d', '30d' => 'telemetry_agg_1h', // Для длительных периодов тоже часовые
            default => 'telemetry_agg_1h',
        };

        try {
            // Используем raw SQL для работы с агрегированными данными
            $query = "
                SELECT 
                    ts,
                    AVG(value_avg) as avg_value,
                    MIN(value_min) as min_value,
                    MAX(value_max) as max_value,
                    AVG(value_median) as median_value
                FROM {$table}
                WHERE zone_id = ?
                    AND metric_type = ?
                    AND ts >= ?
                    AND ts <= ?
                GROUP BY ts
                ORDER BY ts ASC
            ";

            $rows = \Illuminate\Support\Facades\DB::select($query, [
                $zoneId,
                $metric,
                $from->toDateTimeString(),
                $now->toDateTimeString(),
            ]);

            // Преобразуем результаты в массив
            $data = array_map(function ($row) {
                return [
                    'ts' => $row->ts,
                    'avg' => (float) ($row->avg_value ?? 0),
                    'min' => (float) ($row->min_value ?? 0),
                    'max' => (float) ($row->max_value ?? 0),
                    'median' => (float) ($row->median_value ?? 0),
                ];
            }, $rows);

            return response()->json([
                'status' => 'ok',
                'data' => $data,
            ]);
        } catch (\Exception $e) {
            // Если таблица агрегации не существует или произошла ошибка,
            // возвращаем данные из raw samples с более простой агрегацией
            Log::warning('Failed to get aggregates from aggregated table, falling back to raw samples', [
                'error' => $e->getMessage(),
                'table' => $table,
            ]);

            // Fallback: используем raw samples с date_trunc
            $query = "
                SELECT 
                    date_trunc('hour', ts) as ts,
                    AVG(value) as avg_value,
                    MIN(value) as min_value,
                    MAX(value) as max_value
                FROM telemetry_samples
                WHERE zone_id = ?
                    AND metric_type = ?
                    AND ts >= ?
                    AND ts <= ?
                GROUP BY date_trunc('hour', ts)
                ORDER BY ts ASC
            ";

            $rows = \Illuminate\Support\Facades\DB::select($query, [
                $zoneId,
                $metric,
                $from->toDateTimeString(),
                $now->toDateTimeString(),
            ]);

            $data = array_map(function ($row) {
                return [
                    'ts' => $row->ts,
                    'avg' => (float) $row->avg_value,
                    'min' => (float) $row->min_value,
                    'max' => (float) $row->max_value,
                    'median' => (float) $row->avg_value, // Приблизительно
                ];
            }, $rows);

            return response()->json([
                'status' => 'ok',
                'data' => $data,
            ]);
        }
    }
}


