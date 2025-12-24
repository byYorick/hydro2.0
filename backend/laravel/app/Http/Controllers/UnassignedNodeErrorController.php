<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class UnassignedNodeErrorController extends Controller
{
    /**
     * Получить список ошибок неназначенных узлов.
     * 
     * @param Request $request
     * @return JsonResponse
     */
    public function index(Request $request): JsonResponse
    {
        $query = DB::table('unassigned_node_errors')
            ->select([
                'id',
                'hardware_id',
                'error_message',
                'error_code',
                'error_level',
                'topic',
                'error_data',
                'count',
                'first_seen_at',
                'last_seen_at',
                'node_id',
                'created_at',
                'updated_at'
            ])
            ->orderBy('last_seen_at', 'desc');
        
        // Фильтр по hardware_id
        if ($request->has('hardware_id')) {
            $query->where('hardware_id', $request->input('hardware_id'));
        }
        
        // Фильтр по node_id (null = неназначенные, не null = назначенные)
        if ($request->has('unassigned_only')) {
            $query->whereNull('node_id');
        }
        
        // Фильтр по error_level
        if ($request->has('error_level')) {
            $query->where('error_level', $request->input('error_level'));
        }
        
        // Пагинация
        $perPage = min($request->input('per_page', 50), 100);
        $errors = $query->paginate($perPage);
        
        return response()->json([
            'data' => $errors->items(),
            'meta' => [
                'current_page' => $errors->currentPage(),
                'last_page' => $errors->lastPage(),
                'per_page' => $errors->perPage(),
                'total' => $errors->total(),
            ]
        ]);
    }
    
    /**
     * Получить статистику ошибок.
     * 
     * @return JsonResponse
     */
    public function stats(): JsonResponse
    {
        $stats = DB::table('unassigned_node_errors')
            ->selectRaw('
                COUNT(*) as total_errors,
                COUNT(DISTINCT hardware_id) as unique_hardware_ids,
                COUNT(CASE WHEN node_id IS NULL THEN 1 END) as unassigned_count,
                COUNT(CASE WHEN node_id IS NOT NULL THEN 1 END) as assigned_count,
                SUM(count) as total_occurrences,
                MAX(last_seen_at) as latest_error_at
            ')
            ->first();
        
        $byLevel = DB::table('unassigned_node_errors')
            ->select('error_level', DB::raw('COUNT(*) as count'))
            ->groupBy('error_level')
            ->get()
            ->pluck('count', 'error_level');
        
        return response()->json([
            'data' => [
                'total_errors' => (int) $stats->total_errors,
                'unique_hardware_ids' => (int) $stats->unique_hardware_ids,
                'unassigned_count' => (int) $stats->unassigned_count,
                'assigned_count' => (int) $stats->assigned_count,
                'total_occurrences' => (int) $stats->total_occurrences,
                'latest_error_at' => $stats->latest_error_at,
                'by_level' => $byLevel,
            ]
        ]);
    }
    
    /**
     * Получить ошибки для конкретного hardware_id.
     * 
     * @param string $hardwareId
     * @return JsonResponse
     */
    public function show(string $hardwareId): JsonResponse
    {
        $errors = DB::table('unassigned_node_errors')
            ->where('hardware_id', $hardwareId)
            ->orderBy('last_seen_at', 'desc')
            ->get();
        
        return response()->json([
            'data' => $errors
        ]);
    }
}
