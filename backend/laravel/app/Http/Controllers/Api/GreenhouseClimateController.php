<?php

namespace App\Http\Controllers\Api;

use App\Helpers\ZoneAccessHelper;
use App\Http\Controllers\Controller;
use App\Http\Requests\GreenhouseClimate\DeleteGreenhouseClimateManualOverrideRequest;
use App\Http\Requests\GreenhouseClimate\StoreGreenhouseClimateManualOverrideRequest;
use App\Http\Requests\GreenhouseClimate\UpdateGreenhouseClimateControlModeRequest;
use App\Models\Greenhouse;
use App\Models\GreenhouseAutomationState;
use Carbon\CarbonImmutable;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class GreenhouseClimateController extends Controller
{
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

        return response()->json(['status' => 'ok', 'data' => ['id' => $id, 'expires_at' => $expires->toIso8601String()]]);
    }

    public function destroyManualOverride(DeleteGreenhouseClimateManualOverrideRequest $request, Greenhouse $greenhouse): JsonResponse
    {
        abort_unless(ZoneAccessHelper::canAccessGreenhouseScope($request->user(), $greenhouse), 403);

        DB::table('greenhouse_manual_overrides')
            ->where('greenhouse_id', $greenhouse->id)
            ->delete();

        return response()->json(['status' => 'ok']);
    }
}
