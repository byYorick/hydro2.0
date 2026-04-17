<?php

namespace App\Http\Controllers;

use App\Http\Requests\StoreZoneAutomationPresetRequest;
use App\Http\Requests\UpdateZoneAutomationPresetRequest;
use App\Services\ZoneAutomationPresetService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class ZoneAutomationPresetController extends Controller
{
    public function __construct(
        private readonly ZoneAutomationPresetService $presets,
    ) {
    }

    public function index(Request $request): JsonResponse
    {
        $filters = array_filter([
            'tanks_count' => $request->query('tanks_count') !== null
                ? (int) $request->query('tanks_count')
                : null,
            'irrigation_system_type' => $request->query('irrigation_system_type'),
        ], fn ($v) => $v !== null);

        return response()->json([
            'status' => 'ok',
            'data' => $this->presets->list($filters),
        ]);
    }

    public function store(StoreZoneAutomationPresetRequest $request): JsonResponse
    {
        $preset = $this->presets->create(
            $request->validated(),
            $request->user()?->id,
        );

        return response()->json([
            'status' => 'ok',
            'data' => $this->presets->serialize($preset),
        ], Response::HTTP_CREATED);
    }

    public function show(int $preset): JsonResponse
    {
        return response()->json([
            'status' => 'ok',
            'data' => $this->presets->serialize($this->presets->findOrFail($preset)),
        ]);
    }

    public function update(UpdateZoneAutomationPresetRequest $request, int $preset): JsonResponse
    {
        try {
            $updated = $this->presets->update(
                $this->presets->findOrFail($preset),
                $request->validated(),
                $request->user()?->id,
            );

            return response()->json([
                'status' => 'ok',
                'data' => $this->presets->serialize($updated),
            ]);
        } catch (\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function destroy(int $preset): JsonResponse
    {
        try {
            $this->presets->delete($this->presets->findOrFail($preset));

            return response()->json(['status' => 'ok']);
        } catch (\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function duplicate(Request $request, int $preset): JsonResponse
    {
        $created = $this->presets->duplicate(
            $this->presets->findOrFail($preset),
            $request->user()?->id,
        );

        return response()->json([
            'status' => 'ok',
            'data' => $this->presets->serialize($created),
        ], Response::HTTP_CREATED);
    }
}
