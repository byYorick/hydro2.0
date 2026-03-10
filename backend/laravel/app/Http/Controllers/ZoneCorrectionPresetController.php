<?php

namespace App\Http\Controllers;

use App\Http\Requests\UpsertZoneCorrectionPresetRequest;
use App\Models\ZoneCorrectionPreset;
use App\Services\ZoneCorrectionPresetService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Auth;

class ZoneCorrectionPresetController extends Controller
{
    public function __construct(
        private ZoneCorrectionPresetService $presetService,
    ) {
    }

    public function index(): JsonResponse
    {
        return response()->json([
            'status' => 'ok',
            'data' => $this->presetService->list(),
        ]);
    }

    public function store(UpsertZoneCorrectionPresetRequest $request): JsonResponse
    {
        try {
            $preset = $this->presetService->create($request->validated(), Auth::id());

            return response()->json([
                'status' => 'ok',
                'data' => $this->presetService->list(),
                'selected' => $preset->id,
            ], Response::HTTP_CREATED);
        } catch (\InvalidArgumentException|\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function update(UpsertZoneCorrectionPresetRequest $request, ZoneCorrectionPreset $preset): JsonResponse
    {
        try {
            $this->presetService->update($preset, $request->validated(), Auth::id());

            return response()->json([
                'status' => 'ok',
                'data' => $this->presetService->list(),
            ]);
        } catch (\InvalidArgumentException|\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function destroy(ZoneCorrectionPreset $preset): JsonResponse
    {
        try {
            $this->presetService->delete($preset);

            return response()->json([
                'status' => 'ok',
                'data' => $this->presetService->list(),
            ]);
        } catch (\InvalidArgumentException|\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }
}
