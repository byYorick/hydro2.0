<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\AutomationEffectiveBundle;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigRegistry;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class AutomationBundleController extends Controller
{
    public function __construct(
        private readonly AutomationConfigCompiler $compiler,
    ) {
    }

    public function show(Request $request, string $scopeType, int $scopeId): JsonResponse
    {
        $this->assertSupportedBundleScope($scopeType);
        $this->authorizeScopeAccess($request, $scopeType, $scopeId);

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->first();

        if (! $bundle) {
            return response()->json([
                'status' => 'error',
                'message' => 'Automation bundle not found.',
            ], 404);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $this->serializeBundle($bundle),
        ]);
    }

    public function validate(Request $request, string $scopeType, int $scopeId): JsonResponse
    {
        $this->assertSupportedBundleScope($scopeType);
        $this->authorizeScopeAccess($request, $scopeType, $scopeId);

        $this->compiler->compileAffectedScopes($scopeType, $scopeId);
        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->firstOrFail();

        return response()->json([
            'status' => 'ok',
            'data' => $this->serializeBundle($bundle),
        ]);
    }

    /**
     * @return array<string, mixed>
     */
    private function serializeBundle(AutomationEffectiveBundle $bundle): array
    {
        return [
            'scope_type' => $bundle->scope_type,
            'scope_id' => (int) $bundle->scope_id,
            'bundle_revision' => $bundle->bundle_revision,
            'status' => $bundle->status,
            'config' => is_array($bundle->config) ? $bundle->config : [],
            'violations' => is_array($bundle->violations) ? $bundle->violations : [],
            'compiled_at' => $bundle->compiled_at?->toIso8601String(),
        ];
    }

    private function assertSupportedBundleScope(string $scopeType): void
    {
        if (! in_array($scopeType, [
            AutomationConfigRegistry::SCOPE_SYSTEM,
            AutomationConfigRegistry::SCOPE_ZONE,
            AutomationConfigRegistry::SCOPE_GROW_CYCLE,
        ], true)) {
            abort(422, "Unsupported scope type {$scopeType}.");
        }
    }

    private function authorizeScopeAccess(Request $request, string $scopeType, int $scopeId): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_SYSTEM) {
            if (! $user->isAdmin()) {
                abort(403, 'Forbidden: Access denied to system automation bundle');
            }

            return;
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_ZONE) {
            $zone = Zone::query()->findOrFail($scopeId);
            if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                abort(403, 'Forbidden: Access denied to this zone bundle');
            }

            return;
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_GROW_CYCLE) {
            $cycle = GrowCycle::query()->findOrFail($scopeId);
            $zone = Zone::query()->findOrFail((int) $cycle->zone_id);
            if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                abort(403, 'Forbidden: Access denied to this grow cycle bundle');
            }

            return;
        }
    }
}
