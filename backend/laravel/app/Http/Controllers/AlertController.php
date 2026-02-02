<?php

namespace App\Http\Controllers;

use App\Models\Alert;
use App\Services\AlertService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class AlertController extends Controller
{
    public function __construct(
        private AlertService $alertService
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

        // Получаем список доступных зон для пользователя
        $accessibleZoneIds = \App\Helpers\ZoneAccessHelper::getAccessibleZoneIds($user);

        // Eager loading для предотвращения N+1 запросов
        $query = Alert::query()
            ->with(['zone:id,name,status']); // Загружаем только нужные поля зоны

        // Если запрашивается конкретная зона, проверяем доступ к ней
        if ($request->filled('zone_id')) {
            $requestedZoneId = $request->integer('zone_id');
            // Проверяем, что запрашиваемая зона доступна пользователю
            if (! empty($accessibleZoneIds) && in_array($requestedZoneId, $accessibleZoneIds)) {
                $query->where('zone_id', $requestedZoneId);
            } else {
                // Если запрашиваемая зона недоступна, возвращаем пустой результат
                $query->whereRaw('1 = 0');
            }
        } elseif (! empty($accessibleZoneIds)) {
            // Если конкретная зона не запрашивается, фильтруем по всем доступным зонам
            $query->whereIn('zone_id', $accessibleZoneIds);
        } else {
            // Если у пользователя нет доступа ни к одной зоне, не возвращаем алерты
            $query->whereRaw('1 = 0');
        }
        if ($request->filled('status')) {
            $status = strtoupper(trim($request->string('status')->toString()));
            if (in_array($status, ['ACTIVE', 'RESOLVED'], true)) {
                $query->where('status', $status);
            }
        }
        $items = $query->orderByDesc('id')->paginate(50);

        // Фильтрация по зонам уже выполнена выше через whereIn('zone_id', $accessibleZoneIds)
        // Это гарантирует, что пользователь видит только алерты из своих зон
        return response()->json(['status' => 'ok', 'data' => $items]);
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

        // Проверяем доступ к зоне алерта
        if (! \App\Helpers\ZoneAccessHelper::canAccessZone($user, $alert->zone_id)) {
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

        // Проверяем доступ к зоне алерта
        if (! \App\Helpers\ZoneAccessHelper::canAccessZone($user, $alert->zone_id)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this alert',
            ], 403);
        }

        try {
            $alert = $this->alertService->acknowledge($alert);

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
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем наличие pending_alert в DLQ
        $pendingAlert = \Illuminate\Support\Facades\DB::table('pending_alerts')
            ->where('id', $id)
            ->where('status', 'dlq')
            ->first();

        if (!$pendingAlert) {
            return response()->json([
                'status' => 'error',
                'message' => 'Pending alert not found in DLQ',
            ], 404);
        }

        // Проверяем доступ к зоне (если есть)
        if ($pendingAlert->zone_id && !\App\Helpers\ZoneAccessHelper::canAccessZone($user, $pendingAlert->zone_id)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied',
            ], 403);
        }

        try {
            // Обновляем статус обратно на pending и сбрасываем счетчик попыток
            \Illuminate\Support\Facades\DB::table('pending_alerts')
                ->where('id', $id)
                ->update([
                    'status' => 'pending',
                    'attempts' => 0,
                    'last_error' => null,
                    'last_attempt_at' => null,
                    'updated_at' => now(),
                ]);

            // Создаем Job для обработки алерта
            $alertData = [
                'zone_id' => $pendingAlert->zone_id,
                'source' => $pendingAlert->source ?? 'biz',
                'code' => $pendingAlert->code,
                'type' => $pendingAlert->type,
                'details' => $pendingAlert->details ? json_decode($pendingAlert->details, true) : null,
            ];

            \App\Jobs\ProcessAlert::dispatch($alertData, $id);

            return response()->json([
                'status' => 'ok',
                'message' => 'Alert queued for replay',
                'data' => ['pending_alert_id' => $id],
            ], Response::HTTP_OK);

        } catch (\Exception $e) {
            return response()->json([
                'status' => 'error',
                'message' => 'Failed to replay alert: ' . $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }
}
