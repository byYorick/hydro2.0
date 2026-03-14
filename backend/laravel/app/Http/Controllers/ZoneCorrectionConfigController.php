<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Requests\UpdateZoneCorrectionConfigRequest;
use App\Models\Zone;
use App\Services\ZoneCorrectionConfigService;
use App\Services\ZoneCorrectionPresetService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Auth;

class ZoneCorrectionConfigController extends Controller
{
    public function __construct(
        private ZoneCorrectionConfigService $configService,
        private ZoneCorrectionPresetService $presetService,
    ) {
    }

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);
        try {
            return response()->json([
                'status' => 'ok',
                'data' => array_merge(
                    $this->configService->getResponsePayload($zone),
                    ['available_presets' => $this->presetService->list()]
                ),
            ]);
        } catch (\InvalidArgumentException|\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function update(UpdateZoneCorrectionConfigRequest $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        try {
            $config = $this->configService->upsert(
                $zone,
                $request->validated(),
                Auth::id(),
            );

            return response()->json([
                'status' => 'ok',
                'data' => array_merge(
                    $this->configService->getResponsePayload($zone),
                    ['available_presets' => $this->presetService->list()]
                ),
            ]);
        } catch (\InvalidArgumentException|\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function history(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        return response()->json([
            'status' => 'ok',
            'data' => $this->configService->listVersions($zone),
        ]);
    }

    private function authorizeZoneAccess(Request $request, Zone $zone): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            abort(403, 'Forbidden: Access denied to this zone');
        }
    }
}
