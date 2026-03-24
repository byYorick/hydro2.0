<?php

namespace App\Http\Controllers;

use App\Services\AutomationConfigPresetService;
use App\Services\AutomationConfigRegistry;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class AutomationPresetController extends Controller
{
    public function __construct(
        private readonly AutomationConfigPresetService $presets,
        private readonly AutomationConfigRegistry $registry,
    ) {
    }

    public function index(string $namespace): JsonResponse
    {
        return response()->json([
            'status' => 'ok',
            'data' => $this->presets->list($namespace),
        ]);
    }

    public function store(Request $request, string $namespace): JsonResponse
    {
        try {
            $preset = $this->presets->create($namespace, [
                'name' => $request->input('name'),
                'description' => $request->input('description'),
                'payload' => $request->input('payload', []),
            ], $request->user()?->id);

            return response()->json([
                'status' => 'ok',
                'data' => $this->presets->serialize($preset),
            ], Response::HTTP_CREATED);
        } catch (\InvalidArgumentException|\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function update(Request $request, int $preset): JsonResponse
    {
        try {
            $presetModel = $this->presets->findOrFail($preset);
            $updated = $this->presets->update($presetModel, [
                'name' => $request->input('name', $presetModel->name),
                'description' => $request->input('description', $presetModel->description),
                'payload' => $request->input('payload', $presetModel->payload ?? []),
            ], $request->user()?->id);

            return response()->json([
                'status' => 'ok',
                'data' => $this->presets->serialize($updated),
            ]);
        } catch (\InvalidArgumentException|\DomainException $exception) {
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

            return response()->json([
                'status' => 'ok',
            ]);
        } catch (\InvalidArgumentException|\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function duplicate(Request $request, int $preset): JsonResponse
    {
        try {
            $created = $this->presets->duplicate(
                $this->presets->findOrFail($preset),
                $request->user()?->id
            );

            return response()->json([
                'status' => 'ok',
                'data' => $this->presets->serialize($created),
            ], Response::HTTP_CREATED);
        } catch (\InvalidArgumentException|\DomainException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }
}
