<?php

namespace App\Http\Controllers;

use App\Http\Requests\UpsertZoneAutomationLogicProfileRequest;
use App\Models\Zone;
use App\Services\ZoneAutomationLogicProfileService;
use Illuminate\Http\JsonResponse;

class ZoneAutomationLogicProfileController extends Controller
{
    public function __construct(
        private readonly ZoneAutomationLogicProfileService $profiles,
    ) {
    }

    /**
     * Получить профили логики автоматики зоны.
     */
    public function show(Zone $zone): JsonResponse
    {
        $this->authorize('view', $zone);

        return response()->json([
            'status' => 'ok',
            'data' => $this->profiles->getProfilesPayload($zone),
        ]);
    }

    /**
     * Сохранить профиль логики автоматики зоны.
     */
    public function upsert(UpsertZoneAutomationLogicProfileRequest $request, Zone $zone): JsonResponse
    {
        $this->authorize('update', $zone);

        $validated = $request->validated();
        $mode = (string) $validated['mode'];
        $subsystems = is_array($validated['subsystems']) ? $validated['subsystems'] : [];
        $activate = (bool) ($validated['activate'] ?? true);

        $this->profiles->upsertProfile($zone, $mode, $subsystems, $activate, $request->user()?->id);

        return response()->json([
            'status' => 'ok',
            'data' => $this->profiles->getProfilesPayload($zone),
        ]);
    }
}
