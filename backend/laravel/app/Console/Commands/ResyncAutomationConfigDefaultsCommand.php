<?php

namespace App\Console\Commands;

use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneCorrectionConfigCatalog;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Throwable;

/**
 * Подтягивает значения по умолчанию из catalog в существующие automation_config_documents,
 * у которых после Phase 1 patch (ec_dosing_mode + prepare_recirculation_correction_slack_sec)
 * payload оказался неполным.
 *
 * Pre-flight для Phase 3.x рефакторинга: handlers переключаются на strict Pydantic
 * валидацию и нетерпимы к missing required fields. Без этой команды старые зоны не
 * стартуют после релиза Phase 3.
 *
 * Поведение:
 *  - Только zone.correction documents (расширяется по namespace при необходимости).
 *  - Только missing top-level keys внутри base_config.* — НЕ перетирает существующие значения.
 *  - --dry-run: выводит, что будет изменено, без записи.
 *  - --recompile: сразу триггерит compileZoneBundle для каждого затронутого scope.
 *
 * См. doc_ai/04_BACKEND_CORE/AE3_CONFIG_REFACTORING_PLAN.md §«Audit fixes / Pre-flight»
 */
class ResyncAutomationConfigDefaultsCommand extends Command
{
    protected $signature = 'automation_config:resync-defaults
        {--namespace= : Limit to one namespace (default: zone.correction)}
        {--dry-run : Show changes without writing}
        {--recompile : Recompile zone bundles after resync}';

    protected $description = 'Resync missing default fields into existing automation_config_documents (post Phase 1 catalog patch)';

    public function handle(
        AutomationConfigDocumentService $documents,
        AutomationConfigCompiler $compiler,
    ): int {
        $namespace = $this->option('namespace') ?: AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION;
        $dryRun = (bool) $this->option('dry-run');
        $recompile = (bool) $this->option('recompile');

        if ($namespace !== AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION) {
            $this->error("Only zone.correction is supported in this command (got: {$namespace})");
            return self::FAILURE;
        }

        $rows = DB::table('automation_config_documents')
            ->where('namespace', $namespace)
            ->orderBy('scope_id')
            ->get();

        if ($rows->isEmpty()) {
            $this->info("No documents found for {$namespace}.");
            return self::SUCCESS;
        }

        $defaults = ZoneCorrectionConfigCatalog::defaults();
        $touchedScopes = [];
        $changed = 0;

        foreach ($rows as $row) {
            $payload = is_string($row->payload) ? json_decode($row->payload, true) : $row->payload;
            if (!is_array($payload)) {
                $this->warn("scope_id={$row->scope_id}: payload is not JSON object, skipping");
                continue;
            }

            $base = $payload['base_config'] ?? [];
            if (!is_array($base)) {
                $this->warn("scope_id={$row->scope_id}: base_config missing/invalid, skipping");
                continue;
            }

            [$mergedBase, $missingPaths] = $this->fillMissingDefaults($defaults, $base);
            if (empty($missingPaths)) {
                continue;
            }

            $changed++;
            $missingPretty = implode(', ', $missingPaths);
            $this->line("scope_id={$row->scope_id}: missing {$missingPretty}");

            if ($dryRun) {
                continue;
            }

            $payload['base_config'] = $mergedBase;
            try {
                $documents->upsertDocument(
                    $namespace,
                    $row->scope_type,
                    (int) $row->scope_id,
                    $payload,
                    null,
                    'resync-defaults',
                );
                $touchedScopes[(int) $row->scope_id] = $row->scope_type;
            } catch (Throwable $e) {
                $this->error("scope_id={$row->scope_id}: upsert failed: {$e->getMessage()}");
                return self::FAILURE;
            }
        }

        $this->info("Documents updated: {$changed} of {$rows->count()}.");

        if ($recompile && !$dryRun && !empty($touchedScopes)) {
            foreach ($touchedScopes as $scopeId => $scopeType) {
                if ($scopeType === AutomationConfigRegistry::SCOPE_ZONE) {
                    $compiler->compileZoneCascade($scopeId);
                    $this->line("recompiled zone bundle: zone_id={$scopeId}");
                }
            }
        }

        return self::SUCCESS;
    }

    /**
     * Recursively merge missing keys from $defaults into $existing (existing wins).
     *
     * Returns [merged_array, list_of_dot_paths_that_were_added].
     *
     * @param array<string,mixed> $defaults
     * @param array<string,mixed> $existing
     * @return array{0: array<string,mixed>, 1: list<string>}
     */
    private function fillMissingDefaults(array $defaults, array $existing, string $prefix = ''): array
    {
        $missing = [];
        foreach ($defaults as $key => $defaultValue) {
            $path = $prefix === '' ? (string) $key : "{$prefix}.{$key}";
            if (!array_key_exists($key, $existing)) {
                $existing[$key] = $defaultValue;
                $missing[] = $path;
                continue;
            }
            if (is_array($defaultValue) && is_array($existing[$key]) && !array_is_list($defaultValue)) {
                [$existing[$key], $sub] = $this->fillMissingDefaults($defaultValue, $existing[$key], $path);
                $missing = array_merge($missing, $sub);
            }
        }
        return [$existing, $missing];
    }
}
