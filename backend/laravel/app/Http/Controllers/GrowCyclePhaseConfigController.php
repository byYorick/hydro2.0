<?php

namespace App\Http\Controllers;

use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\Zone;
use App\Services\AutomationConfigCompiler;
use App\Services\ZoneConfigRevisionService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Validation\Rule;

/**
 * Phase 5.6: live edit активной recipe phase в текущем цикле (Q4).
 *
 * Разрешён ТОЛЬКО когда `zones.config_mode = 'live'` — редактирование
 * параметров активной фазы напрямую в `grow_cycle_phases.X` без смены
 * фаз. После апдейта:
 *   1. compileGrowCycleBundle(grow_cycle_id) пересобирает snapshot
 *   2. ZoneConfigRevisionService инкрементирует zones.config_revision
 *   3. AE3 `_checkpoint()` подхватывает fresh RuntimePlan на next run()
 *
 * Затрагивает только "безопасные" setpoint-поля (pH/EC targets + mins/maxes,
 * irrigation/lighting интервалы). Изменение substrate_type, irrigation_mode,
 * phase_index запрещено — это ломает topology/plan structure.
 */
class GrowCyclePhaseConfigController extends Controller
{
    /** Safe-to-edit fields in live mode. Extended carefully (audit). */
    private const LIVE_EDITABLE_FIELDS = [
        'ph_target', 'ph_min', 'ph_max',
        'ec_target', 'ec_min', 'ec_max',
        'temp_air_target', 'humidity_target', 'co2_target',
        'irrigation_interval_sec', 'irrigation_duration_sec',
        'lighting_photoperiod_hours', 'lighting_start_time',
        'mist_interval_sec', 'mist_duration_sec',
    ];

    public function __construct(
        private readonly AutomationConfigCompiler $compiler,
        private readonly ZoneConfigRevisionService $revisionService,
    ) {}

    public function update(Request $request, GrowCycle $growCycle): JsonResponse
    {
        $user = $request->user();
        if ($user === null) {
            return response()->json(['status' => 'error', 'code' => 'UNAUTHENTICATED'], 401);
        }

        $zone = Zone::find($growCycle->zone_id);
        if ($zone === null) {
            return response()->json(['status' => 'error', 'code' => 'ZONE_NOT_FOUND'], 404);
        }

        if (! $user->can('setLive', $zone)) {
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN_SET_LIVE',
                'message' => 'Роль не позволяет править phase-config.',
            ], 403);
        }

        // Phase 5.6 invariant: live edit of recipe phase — только в live mode.
        if (($zone->config_mode ?? 'locked') !== 'live') {
            return response()->json([
                'status' => 'error',
                'code' => 'ZONE_NOT_IN_LIVE_MODE',
                'message' => 'Редактирование активной фазы доступно только в config_mode=live.',
            ], 409);
        }

        if ($growCycle->current_phase_id === null) {
            return response()->json([
                'status' => 'error',
                'code' => 'NO_ACTIVE_PHASE',
                'message' => 'У цикла нет активной фазы.',
            ], 409);
        }

        $editableRules = [];
        foreach (self::LIVE_EDITABLE_FIELDS as $f) {
            $editableRules[$f] = ['nullable', 'numeric'];
        }
        $editableRules['lighting_start_time'] = ['nullable', 'date_format:H:i,H:i:s'];

        $validated = $request->validate(array_merge(
            ['reason' => ['required', 'string', 'min:3', 'max:500']],
            $editableRules,
        ));
        $reason = $validated['reason'];
        unset($validated['reason']);

        $fields = array_intersect_key($validated, array_flip(self::LIVE_EDITABLE_FIELDS));
        // Drop unchanged keys to keep diff signal clean.
        $fields = array_filter($fields, fn ($v) => $v !== null);
        if (empty($fields)) {
            return response()->json([
                'status' => 'error',
                'code' => 'NO_FIELDS_PROVIDED',
                'message' => 'Передай хотя бы одно поле из whitelist.',
                'details' => ['allowed' => self::LIVE_EDITABLE_FIELDS],
            ], 422);
        }

        $result = DB::transaction(function () use ($growCycle, $fields, $reason, $user, $zone): array {
            /** @var GrowCyclePhase|null $phase */
            $phase = GrowCyclePhase::lockForUpdate()->find($growCycle->current_phase_id);
            if ($phase === null) {
                return ['status' => 404, 'code' => 'PHASE_NOT_FOUND'];
            }

            $before = [];
            foreach ($fields as $k => $_) {
                $before[$k] = $phase->{$k};
            }
            $phase->forceFill($fields)->save();

            // Recompile grow_cycle bundle → AE3 snapshot (на следующем reload)
            // увидит свежие targets. Без этого zone bundle пересобирается, но
            // grow_cycle остаётся со старыми phase targets.
            $this->compiler->compileGrowCycleBundle($growCycle->id);

            // Bump zones.config_revision + audit row (pylint: через service
            // атомарного UPDATE ... RETURNING).
            $revision = $this->revisionService->bumpAndAudit(
                scopeType: 'zone',
                scopeId: $growCycle->zone_id,
                namespace: 'recipe.phase',
                diff: [
                    'grow_cycle_id' => $growCycle->id,
                    'phase_id' => $phase->id,
                    'phase_name' => $phase->name,
                    'before' => $before,
                    'after' => $fields,
                ],
                userId: $user->id,
                reason: $reason,
            );

            return ['status' => 200, 'revision' => $revision, 'phase' => $phase];
        });

        if ($result['status'] !== 200) {
            return response()->json([
                'status' => 'error',
                'code' => $result['code'] ?? 'ERROR',
            ], $result['status']);
        }

        Log::info('grow_cycle.phase_config.live_edited', [
            'grow_cycle_id' => $growCycle->id,
            'zone_id' => $growCycle->zone_id,
            'phase_id' => $result['phase']->id,
            'user_id' => $user->id,
            'fields' => array_keys($fields),
            'new_revision' => $result['revision'],
        ]);

        return response()->json([
            'status' => 'ok',
            'grow_cycle_id' => $growCycle->id,
            'phase_id' => $result['phase']->id,
            'zone_id' => $growCycle->zone_id,
            'config_revision' => $result['revision'],
            'updated_fields' => array_keys($fields),
        ]);
    }
}
