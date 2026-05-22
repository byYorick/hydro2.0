<?php

namespace App\Http\Controllers\Api;

use App\Helpers\ZoneAccessHelper;
use App\Http\Controllers\Controller;
use App\Http\Requests\GreenhouseClimate\DeleteGreenhouseClimateManualOverrideRequest;
use App\Http\Requests\GreenhouseClimate\StoreGreenhouseClimateManualOverrideRequest;
use App\Http\Requests\GreenhouseClimate\UpdateGreenhouseClimateControlModeRequest;
use App\Models\Greenhouse;
use App\Models\GreenhouseAutomationState;
use App\Services\GreenhouseClimate\GreenhouseClimateDispatchService;
use Carbon\CarbonImmutable;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class GreenhouseClimateController extends Controller
{
    public function __construct(
        private readonly GreenhouseClimateDispatchService $dispatchService,
    ) {
    }

    public function state(Request $request, Greenhouse $greenhouse): JsonResponse
    {
        abort_unless(ZoneAccessHelper::canAccessGreenhouseScope($request->user(), $greenhouse), 403);

        $state = GreenhouseAutomationState::query()->firstOrCreate(
            ['greenhouse_id' => $greenhouse->id],
            [
                'climate_enabled' => false,
                'control_mode' => 'auto',
            ]
        );

        return response()->json([
            'status' => 'ok',
            'data' => [
                'greenhouse_id' => $greenhouse->id,
                'state' => $state,
            ],
        ]);
    }

    public function updateControlMode(UpdateGreenhouseClimateControlModeRequest $request, Greenhouse $greenhouse): JsonResponse
    {
        abort_unless(ZoneAccessHelper::canAccessGreenhouseScope($request->user(), $greenhouse), 403);

        $state = GreenhouseAutomationState::query()->firstOrCreate(
            ['greenhouse_id' => $greenhouse->id],
            ['climate_enabled' => false, 'control_mode' => 'auto']
        );
        $state->control_mode = $request->validated('control_mode');
        $state->save();

        return response()->json(['status' => 'ok', 'data' => $state]);
    }

    public function storeManualOverride(StoreGreenhouseClimateManualOverrideRequest $request, Greenhouse $greenhouse): JsonResponse
    {
        abort_unless(ZoneAccessHelper::canAccessGreenhouseScope($request->user(), $greenhouse), 403);

        $ttl = max(1, (int) $request->validated('ttl_sec'));
        $ttl = min($ttl, $this->manualOverrideMaxSec($greenhouse));
        $expires = CarbonImmutable::now('UTC')->addSeconds($ttl);

        $id = DB::table('greenhouse_manual_overrides')->insertGetId([
            'greenhouse_id' => $greenhouse->id,
            'left_position_pct' => (int) $request->validated('left_position_pct'),
            'right_position_pct' => (int) $request->validated('right_position_pct'),
            'ttl_sec' => $ttl,
            'return_mode' => $request->validated('return_mode'),
            'reason' => $request->validated('reason'),
            'expires_at' => $expires,
            'created_by' => $request->user()?->id,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $this->dispatchService->dispatchNow($greenhouse->id, 'manual_override');

        return response()->json(['status' => 'ok', 'data' => ['id' => $id, 'expires_at' => $expires->toIso8601String()]]);
    }

    public function destroyManualOverride(DeleteGreenhouseClimateManualOverrideRequest $request, Greenhouse $greenhouse): JsonResponse
    {
        abort_unless(ZoneAccessHelper::canAccessGreenhouseScope($request->user(), $greenhouse), 403);

        DB::table('greenhouse_manual_overrides')
            ->where('greenhouse_id', $greenhouse->id)
            ->delete();

        $this->dispatchService->dispatchNow($greenhouse->id, 'manual_override_delete');

        return response()->json(['status' => 'ok']);
    }

    private function manualOverrideMaxSec(Greenhouse $greenhouse): int
    {
        $row = DB::table('automation_effective_bundles')
            ->where('scope_type', 'greenhouse')
            ->where('scope_id', $greenhouse->id)
            ->where('status', 'valid')
            ->first();

        $config = is_string($row->config ?? null) ? json_decode((string) $row->config, true) : ($row->config ?? null);
        if (! is_array($config)) {
            return 86400;
        }

        $logicProfile = $config['greenhouse']['logic_profile'] ?? null;
        if (! is_array($logicProfile)) {
            return 86400;
        }
        $mode = $logicProfile['active_mode'] ?? null;
        if (! is_string($mode) || ! in_array($mode, ['setup', 'working'], true)) {
            return 86400;
        }

        $value = $logicProfile['profiles'][$mode]['subsystems']['climate']['execution']['manual_override_max_sec'] ?? null;
        if (! is_numeric($value)) {
            return 86400;
        }

        return max(60, min(86400, (int) $value));
    }
}
