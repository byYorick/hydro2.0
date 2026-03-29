<?php

namespace App\Http\Controllers;

use App\Models\Alert;
use App\Helpers\ZoneAccessHelper;
use App\Services\AlertCatalogService;
use App\Services\AlertService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\DB;

class AlertController extends Controller
{
    public function __construct(
        private AlertService $alertService,
        private AlertCatalogService $alertCatalogService,
    ) {}

    public function index(Request $request)
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);

        $query = Alert::query()
            ->with(['zone:id,name,status']);

        if ($request->filled('zone_id')) {
            $requestedZoneId = $request->integer('zone_id');
            if (! empty($accessibleZoneIds) && in_array($requestedZoneId, $accessibleZoneIds)) {
                $query->where('zone_id', $requestedZoneId);
            } else {
                $query->whereRaw('1 = 0');
            }
        } elseif (! empty($accessibleZoneIds)) {
            $query->where(function ($alertsQuery) use ($accessibleZoneIds) {
                $alertsQuery
                    ->whereIn('zone_id', $accessibleZoneIds)
                    ->orWhereNull('zone_id');
            });
        } else {
            $query->whereNull('zone_id');
        }

        if ($request->filled('status')) {
            $status = strtoupper(trim($request->string('status')->toString()));
            if (in_array($status, ['ACTIVE', 'RESOLVED'], true)) {
                $query->where(function ($statusQuery) use ($status) {
                    $statusQuery
                        ->where('status', $status)
                        ->orWhere('status', strtolower($status));
                });
            }
        }

        if ($request->filled('source')) {
            $source = strtolower(trim($request->string('source')->toString()));
            if (in_array($source, ['biz', 'infra', 'node'], true)) {
                $query->whereRaw('LOWER(source) = ?', [$source]);
            }
        }

        if ($request->filled('severity')) {
            $severity = strtolower(trim($request->string('severity')->toString()));
            if (in_array($severity, ['info', 'warning', 'error', 'critical'], true)) {
                $query->whereRaw("LOWER(COALESCE(severity, '')) = ?", [$severity]);
            }
        }

        if ($request->filled('category')) {
            $category = strtolower(trim($request->string('category')->toString()));
            if (in_array($category, ['agronomy', 'infrastructure', 'operations', 'node', 'config', 'safety', 'other'], true)) {
                $query->whereRaw("LOWER(COALESCE(category, '')) = ?", [$category]);
            }
        }

        if ($request->filled('code')) {
            $code = strtolower(trim($request->string('code')->toString()));
            $query->whereRaw("LOWER(COALESCE(code, '')) LIKE ?", ["%{$code}%"]);
        }

        if ($request->filled('type')) {
            $type = strtolower(trim($request->string('type')->toString()));
            $query->whereRaw("LOWER(COALESCE(type, '')) LIKE ?", ["%{$type}%"]);
        }

        if ($request->filled('node_uid')) {
            $nodeUid = trim($request->string('node_uid')->toString());
            $query->where('node_uid', $nodeUid);
        }

        if ($request->filled('hardware_id')) {
            $hardwareId = trim($request->string('hardware_id')->toString());
            $query->where('hardware_id', $hardwareId);
        }

        if ($request->filled('q')) {
            $needle = trim($request->string('q')->toString());
            $driver = DB::connection()->getDriverName();

            if ($needle !== '') {
                if ($driver === 'pgsql') {
                    $query->where(function ($searchQuery) use ($needle) {
                        $like = "%{$needle}%";
                        $searchQuery
                            ->whereRaw('code ILIKE ?', [$like])
                            ->orWhereRaw('type ILIKE ?', [$like])
                            ->orWhereRaw('source ILIKE ?', [$like])
                            ->orWhereRaw("COALESCE(severity, '') ILIKE ?", [$like])
                            ->orWhereRaw("COALESCE(category, '') ILIKE ?", [$like])
                            ->orWhereRaw("COALESCE(node_uid, '') ILIKE ?", [$like])
                            ->orWhereRaw("COALESCE(hardware_id, '') ILIKE ?", [$like])
                            ->orWhereRaw('CAST(details AS TEXT) ILIKE ?', [$like]);
                    });
                } else {
                    $needleLower = strtolower($needle);
                    $query->where(function ($searchQuery) use ($needleLower) {
                        $like = "%{$needleLower}%";
                        $searchQuery
                            ->whereRaw("LOWER(COALESCE(code, '')) LIKE ?", [$like])
                            ->orWhereRaw("LOWER(COALESCE(type, '')) LIKE ?", [$like])
                            ->orWhereRaw("LOWER(COALESCE(source, '')) LIKE ?", [$like])
                            ->orWhereRaw("LOWER(COALESCE(severity, '')) LIKE ?", [$like])
                            ->orWhereRaw("LOWER(COALESCE(category, '')) LIKE ?", [$like])
                            ->orWhereRaw("LOWER(COALESCE(node_uid, '')) LIKE ?", [$like])
                            ->orWhereRaw("LOWER(COALESCE(hardware_id, '')) LIKE ?", [$like])
                            ->orWhereRaw("LOWER(COALESCE(CAST(details AS CHAR), '')) LIKE ?", [$like]);
                    });
                }
            }
        }

        $items = $query->orderByDesc('id')->paginate(50);

        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function catalog(Request $request)
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'meta' => $this->alertCatalogService->metadata(),
                'items' => $this->alertCatalogService->all(),
            ],
        ]);
    }

    public function show(Request $request, Alert $alert)
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if ($alert->zone_id && ! ZoneAccessHelper::canAccessZone($user, $alert->zone_id)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this alert',
            ], 403);
        }

        return response()->json(['status' => 'ok', 'data' => $alert]);
    }

    public function ack(Request $request, Alert $alert)
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if ($alert->zone_id && ! ZoneAccessHelper::canAccessZone($user, $alert->zone_id)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this alert',
            ], 403);
        }

        try {
            $alert = $this->alertService->acknowledge($alert, [
                'resolved_by' => 'user_ack_api',
                'resolved_via' => 'manual',
                'resolved_by_user_id' => $user->id ?? null,
                'resolved_by_user_name' => $user->name ?? null,
                'resolved_by_user_email' => $user->email ?? null,
                'resolved_ip' => $request->ip(),
            ]);

            return response()->json(['status' => 'ok', 'data' => $alert], Response::HTTP_OK);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    /**
     * Replay алерт из DLQ.
     */
    public function replayDlq(Request $request, int $id)
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $pendingAlert = \Illuminate\Support\Facades\DB::table('pending_alerts_dlq')
            ->where('id', $id)
            ->first();

        if (! $pendingAlert) {
            return response()->json([
                'status' => 'error',
                'message' => 'Pending alert not found in pending_alerts_dlq',
            ], 404);
        }

        if ($pendingAlert->zone_id && ! \App\Helpers\ZoneAccessHelper::canAccessZone($user, $pendingAlert->zone_id)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied',
            ], 403);
        }

        try {
            $newPendingId = null;
            $alertData = null;
            \Illuminate\Support\Facades\DB::transaction(function () use ($pendingAlert, $id, &$newPendingId, &$alertData): void {
                $newPendingId = \Illuminate\Support\Facades\DB::table('pending_alerts')->insertGetId([
                    'zone_id' => $pendingAlert->zone_id,
                    'source' => $pendingAlert->source ?? 'biz',
                    'code' => $pendingAlert->code,
                    'type' => $pendingAlert->type,
                    'status' => 'pending',
                    'details' => $pendingAlert->details,
                    'attempts' => 0,
                    'max_attempts' => $pendingAlert->max_attempts ?? 3,
                    'next_retry_at' => now(),
                    'last_error' => null,
                    'moved_to_dlq_at' => null,
                    'created_at' => now(),
                    'updated_at' => now(),
                ]);

                \Illuminate\Support\Facades\DB::table('pending_alerts_dlq')
                    ->where('id', $id)
                    ->delete();

                $alertData = [
                    'zone_id' => $pendingAlert->zone_id,
                    'source' => $pendingAlert->source ?? 'biz',
                    'code' => $pendingAlert->code,
                    'type' => $pendingAlert->type,
                    'details' => $pendingAlert->details ? json_decode($pendingAlert->details, true) : null,
                ];
            });

            \App\Jobs\ProcessAlert::dispatch($alertData, $newPendingId);

            return response()->json([
                'status' => 'ok',
                'message' => 'Alert queued for replay',
                'data' => ['pending_alert_id' => $newPendingId, 'dlq_id' => $id],
            ], Response::HTTP_OK);
        } catch (\Exception $e) {
            return response()->json([
                'status' => 'error',
                'message' => 'Failed to replay alert: '.$e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }
}
