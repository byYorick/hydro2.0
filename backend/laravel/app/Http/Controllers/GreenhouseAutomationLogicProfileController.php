<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Requests\UpsertGreenhouseAutomationLogicProfileRequest;
use App\Models\Greenhouse;
use App\Services\GreenhouseAutomationLogicProfileService;
use Illuminate\Http\JsonResponse;
use RuntimeException;

class GreenhouseAutomationLogicProfileController extends Controller
{
    public function __construct(
        private readonly GreenhouseAutomationLogicProfileService $profiles,
    ) {
    }

    public function show(Greenhouse $greenhouse): JsonResponse
    {
        $user = request()->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (! ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $this->profiles->getProfilesPayload($greenhouse),
        ]);
    }

    public function upsert(
        UpsertGreenhouseAutomationLogicProfileRequest $request,
        Greenhouse $greenhouse
    ): JsonResponse {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (! ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }

        $validated = $request->validated();
        $mode = (string) $validated['mode'];
        $subsystems = is_array($validated['subsystems']) ? $validated['subsystems'] : [];
        $activate = (bool) ($validated['activate'] ?? true);

        try {
            $this->profiles->upsertProfile($greenhouse, $mode, $subsystems, $activate, $user->id);
        } catch (RuntimeException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], 503);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $this->profiles->getProfilesPayload($greenhouse),
        ]);
    }
}
