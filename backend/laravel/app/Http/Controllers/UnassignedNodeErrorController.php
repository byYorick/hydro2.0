<?php

namespace App\Http\Controllers;

use App\Services\ErrorCodeCatalogService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class UnassignedNodeErrorController extends Controller
{
    public function __construct(
        private readonly ErrorCodeCatalogService $errorCodeCatalog,
    ) {}

    /**
     * Получить список ошибок неназначенных узлов.
     */
    public function index(Request $request): JsonResponse
    {
        $query = DB::table('unassigned_node_errors')
            ->select([
                'id',
                'hardware_id',
                'error_message',
                'error_code',
                'severity',
                'topic',
                'last_payload',
                'count',
                'first_seen_at',
                'last_seen_at',
                'node_id',
                'created_at',
                'updated_at',
            ])
            ->orderBy('last_seen_at', 'desc');

        if ($request->has('hardware_id')) {
            $query->where('hardware_id', $request->input('hardware_id'));
        }

        if ($request->has('unassigned_only')) {
            $query->whereNull('node_id');
        }

        $severity = $request->input('severity') ?? $request->input('error_level');
        if ($severity) {
            $query->where('severity', strtoupper((string) $severity));
        }

        $perPage = min($request->input('per_page', 50), 100);
        $errors = $query->paginate($perPage);
        $items = collect($errors->items())->map(fn ($error) => $this->presentErrorRow((array) $error))->all();

        return response()->json([
            'data' => $items,
            'meta' => [
                'current_page' => $errors->currentPage(),
                'last_page' => $errors->lastPage(),
                'per_page' => $errors->perPage(),
                'total' => $errors->total(),
            ],
        ]);
    }

    /**
     * Получить статистику ошибок.
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

        $bySeverity = DB::table('unassigned_node_errors')
            ->select('severity', DB::raw('COUNT(*) as count'))
            ->groupBy('severity')
            ->get()
            ->pluck('count', 'severity');

        return response()->json([
            'data' => [
                'total_errors' => (int) $stats->total_errors,
                'unique_hardware_ids' => (int) $stats->unique_hardware_ids,
                'unassigned_count' => (int) $stats->unassigned_count,
                'assigned_count' => (int) $stats->assigned_count,
                'total_occurrences' => (int) $stats->total_occurrences,
                'latest_error_at' => $stats->latest_error_at,
                'by_severity' => $bySeverity,
                'by_level' => $bySeverity,
            ],
        ]);
    }

    /**
     * Получить ошибки для конкретного hardware_id.
     */
    public function show(string $hardwareId): JsonResponse
    {
        $errors = DB::table('unassigned_node_errors')
            ->where('hardware_id', $hardwareId)
            ->orderBy('last_seen_at', 'desc')
            ->get()
            ->map(fn ($error) => $this->presentErrorRow((array) $error));

        return response()->json([
            'data' => $errors,
        ]);
    }

    /**
     * @param  array<string, mixed>  $error
     * @return array<string, mixed>
     */
    private function presentErrorRow(array $error): array
    {
        $errorCode = isset($error['error_code']) ? (string) $error['error_code'] : null;
        $errorMessage = isset($error['error_message']) ? (string) $error['error_message'] : null;
        $presentation = $this->errorCodeCatalog->present($errorCode, $errorMessage);
        $error['human_error_message'] = $presentation['message'];

        return $error;
    }
}
