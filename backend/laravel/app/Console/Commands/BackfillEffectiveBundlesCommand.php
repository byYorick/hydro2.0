<?php

namespace App\Console\Commands;

use App\Models\AutomationEffectiveBundle;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigRegistry;
use Illuminate\Console\Command;
use Throwable;

/**
 * Перекомпилирует все automation_effective_bundles и гарантирует наличие
 * обязательных секций в config для всех активных grow_cycles и зон.
 *
 * Необходима как pre-flight для Phase 4.2 (runtime_plan_builder.py cleanup):
 * после удаления isinstance(Mapping) guards builder ожидает, что bundles
 * содержат section zone.process_calibration, zone.pid и
 * cycle.start_snapshot.diagnostics_execution (startup/two_tank_commands).
 *
 * Поведение:
 *  --scope=system|zone|grow_cycle|all  — ограничить scope (по умолчанию all)
 *  --dry-run                            — показать что будет перекомпилировано
 *  --validate-only                      — проверить наличие секций без перекомпиляции
 *
 * ВАЖНО: для production запускать через maintenance window после staging проверки.
 * Команда НЕ выполняется автоматически при migrate — запускать вручную.
 */
class BackfillEffectiveBundlesCommand extends Command
{
    protected $signature = 'automation:backfill-effective-bundles
        {--scope=all : system|zone|grow_cycle|all}
        {--dry-run : Show what would be recompiled without writing}
        {--validate-only : Check sections presence without recompilation}
        {--zone-id= : Limit to specific zone ID}
        {--cycle-id= : Limit to specific grow_cycle ID}';

    protected $description = 'Backfill / recompile automation_effective_bundles ensuring required config sections exist';

    private const REQUIRED_ZONE_SECTIONS = ['zone.logic_profile', 'zone.correction', 'zone.pid', 'zone.process_calibration'];

    private const REQUIRED_CYCLE_SECTIONS = ['zone.correction', 'zone.pid', 'zone.process_calibration', 'cycle.start_snapshot'];

    public function handle(AutomationConfigCompiler $compiler): int
    {
        $scope = $this->option('scope') ?: 'all';
        $dryRun = (bool) $this->option('dry-run');
        $validateOnly = (bool) $this->option('validate-only');
        $zoneId = $this->option('zone-id') ? (int) $this->option('zone-id') : null;
        $cycleId = $this->option('cycle-id') ? (int) $this->option('cycle-id') : null;

        if ($dryRun && $validateOnly) {
            $this->error('Cannot combine --dry-run and --validate-only.');
            return self::FAILURE;
        }

        $validScopes = ['system', 'zone', 'grow_cycle', 'all'];
        if (! in_array($scope, $validScopes, true)) {
            $this->error("Invalid scope: {$scope}. Valid values: " . implode(', ', $validScopes));
            return self::FAILURE;
        }

        $this->line('');
        $this->info("=== automation:backfill-effective-bundles ===");
        if ($dryRun) {
            $this->warn('DRY RUN — no changes will be written');
        }
        if ($validateOnly) {
            $this->warn('VALIDATE ONLY — checking sections presence');
        }
        $this->line('');

        $errors = 0;
        $recompiled = 0;
        $checked = 0;

        if (in_array($scope, ['zone', 'all'], true)) {
            $errors += $this->processZones(
                compiler: $compiler,
                dryRun: $dryRun,
                validateOnly: $validateOnly,
                zoneId: $zoneId,
                recompiled: $recompiled,
                checked: $checked,
            );
        }

        if (in_array($scope, ['grow_cycle', 'all'], true)) {
            $errors += $this->processGrowCycles(
                compiler: $compiler,
                dryRun: $dryRun,
                validateOnly: $validateOnly,
                cycleId: $cycleId,
                recompiled: $recompiled,
                checked: $checked,
            );
        }

        $this->line('');
        $this->info("Checked: {$checked} | Recompiled: {$recompiled} | Errors: {$errors}");

        return $errors > 0 ? self::FAILURE : self::SUCCESS;
    }

    private function processZones(
        AutomationConfigCompiler $compiler,
        bool $dryRun,
        bool $validateOnly,
        ?int $zoneId,
        int &$recompiled,
        int &$checked,
    ): int {
        $query = Zone::query();
        if ($zoneId !== null) {
            $query->where('id', $zoneId);
        }

        $errors = 0;
        $zones = $query->get(['id']);

        $this->line("Zones: {$zones->count()} to process");

        foreach ($zones as $zone) {
            $checked++;
            $zid = (int) $zone->id;
            $bundle = AutomationEffectiveBundle::query()
                ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
                ->where('scope_id', $zid)
                ->first();

            $missing = $this->findMissingSections($bundle, self::REQUIRED_ZONE_SECTIONS);

            if ($missing !== [] || $validateOnly) {
                if ($missing !== []) {
                    $this->warn("  Zone {$zid}: missing sections — " . implode(', ', $missing));
                } else {
                    $this->line("  Zone {$zid}: OK");
                    continue;
                }

                if ($validateOnly) {
                    // Validate-only: report missing sections but never recompile.
                    continue;
                }

                if ($dryRun) {
                    $this->line("  [dry-run] Would recompile zone bundle for zone {$zid}");
                    continue;
                }

                try {
                    $compiler->compileZoneBundle($zid);
                    $this->info("  Zone {$zid}: recompiled ✓");
                    $recompiled++;
                } catch (Throwable $e) {
                    $this->error("  Zone {$zid}: recompile failed — {$e->getMessage()}");
                    $errors++;
                }
            } else {
                $this->line("  Zone {$zid}: OK (all sections present)");
            }
        }

        return $errors;
    }

    private function processGrowCycles(
        AutomationConfigCompiler $compiler,
        bool $dryRun,
        bool $validateOnly,
        ?int $cycleId,
        int &$recompiled,
        int &$checked,
    ): int {
        $query = GrowCycle::query()->active();
        if ($cycleId !== null) {
            $query->where('id', $cycleId);
        }

        $errors = 0;
        $cycles = $query->get(['id', 'zone_id']);

        $this->line("Active grow cycles: {$cycles->count()} to process");

        foreach ($cycles as $cycle) {
            $checked++;
            $cid = (int) $cycle->id;
            $bundle = AutomationEffectiveBundle::query()
                ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
                ->where('scope_id', $cid)
                ->first();

            $missing = $this->findMissingSections($bundle, self::REQUIRED_CYCLE_SECTIONS);

            if ($missing !== [] || $validateOnly) {
                if ($missing !== []) {
                    $this->warn("  Cycle {$cid} (zone {$cycle->zone_id}): missing sections — " . implode(', ', $missing));
                } else {
                    $this->line("  Cycle {$cid}: OK");
                    continue;
                }

                if ($validateOnly) {
                    // Validate-only: report missing sections but never recompile.
                    continue;
                }

                if ($dryRun) {
                    $this->line("  [dry-run] Would recompile grow_cycle bundle for cycle {$cid}");
                    continue;
                }

                try {
                    $compiler->compileGrowCycleBundle($cid);
                    $this->info("  Cycle {$cid}: recompiled ✓");
                    $recompiled++;
                } catch (Throwable $e) {
                    $this->error("  Cycle {$cid}: recompile failed — {$e->getMessage()}");
                    $errors++;
                }
            } else {
                $this->line("  Cycle {$cid}: OK (all sections present)");
            }
        }

        return $errors;
    }

    /**
     * @param  array<string>  $requiredDotPaths
     * @return array<string>
     */
    private function findMissingSections(?AutomationEffectiveBundle $bundle, array $requiredDotPaths): array
    {
        if ($bundle === null) {
            return ['<bundle_missing>'];
        }

        $config = is_array($bundle->config) ? $bundle->config : [];
        $missing = [];

        foreach ($requiredDotPaths as $path) {
            if (data_get($config, $path) === null) {
                $missing[] = $path;
            }
        }

        return $missing;
    }
}
