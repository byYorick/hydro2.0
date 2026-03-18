<?php

namespace App\Http\Controllers;

use App\Models\SystemAutomationSetting;
use App\Services\SystemAutomationSettingsCatalog;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class SystemAutomationSettingsController extends Controller
{
    public function index(): JsonResponse
    {
        $items = [];
        foreach (SystemAutomationSettingsCatalog::namespaces() as $namespace) {
            $items[$namespace] = $this->payloadForNamespace($namespace);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $items,
        ]);
    }

    public function show(string $namespace): JsonResponse
    {
        $this->ensureNamespaceExists($namespace);

        return response()->json([
            'status' => 'ok',
            'data' => $this->payloadForNamespace($namespace),
        ]);
    }

    public function update(Request $request, string $namespace): JsonResponse
    {
        $this->ensureNamespaceExists($namespace);

        try {
            $current = SystemAutomationSetting::forNamespace($namespace);
            $partial = $request->validate(['config' => ['required', 'array']])['config'];
            $validated = SystemAutomationSettingsCatalog::validate($namespace, $partial, true);
            $merged = SystemAutomationSettingsCatalog::merge($current, $validated);
            SystemAutomationSettingsCatalog::validate($namespace, $merged, false);

            SystemAutomationSetting::query()->updateOrCreate(
                ['namespace' => $namespace],
                [
                    'config' => $merged,
                    'updated_by' => $request->user()?->id,
                ],
            );

            return response()->json([
                'status' => 'ok',
                'data' => $this->payloadForNamespace($namespace),
            ]);
        } catch (\InvalidArgumentException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function reset(Request $request, string $namespace): JsonResponse
    {
        $this->ensureNamespaceExists($namespace);
        SystemAutomationSetting::query()->updateOrCreate(
            ['namespace' => $namespace],
            [
                'config' => SystemAutomationSettingsCatalog::defaults($namespace),
                'updated_by' => $request->user()?->id,
            ],
        );

        return response()->json([
            'status' => 'ok',
            'data' => $this->payloadForNamespace($namespace),
        ]);
    }

    private function payloadForNamespace(string $namespace): array
    {
        try {
            return [
                'namespace' => $namespace,
                'config' => SystemAutomationSetting::forNamespace($namespace),
                'meta' => [
                    'defaults' => SystemAutomationSettingsCatalog::defaults($namespace),
                    'field_catalog' => SystemAutomationSettingsCatalog::fieldCatalog($namespace),
                ],
            ];
        } catch (\InvalidArgumentException $exception) {
            abort(404, $exception->getMessage());
        }
    }

    private function ensureNamespaceExists(string $namespace): void
    {
        if (! in_array($namespace, SystemAutomationSettingsCatalog::namespaces(), true)) {
            abort(404, "Namespace {$namespace} not found");
        }
    }
}
