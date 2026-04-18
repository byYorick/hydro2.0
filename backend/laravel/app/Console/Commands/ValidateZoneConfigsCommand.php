<?php

namespace App\Console\Commands;

use App\Services\JsonSchemaValidator;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use RuntimeException;

/**
 * Pre-flight валидация существующих automation_config_documents против новых
 * канонических JSON Schemas (schemas/*.v1.json).
 *
 * Назначение: перед релизом Phase 3 рефакторинга (handlers переключаются на
 * strict Pydantic loader) понять масштаб расхождений данных и schema.
 *
 * Использование:
 *   php artisan zones:validate-configs
 *   php artisan zones:validate-configs --scope=zone
 *   php artisan zones:validate-configs --namespace=zone.correction
 *   php artisan zones:validate-configs --json
 *
 * Exit codes:
 *   0 — все проверенные documents валидны
 *   1 — хотя бы один document имеет violations
 *   2 — некорректные аргументы / схема не найдена
 *
 * См. doc_ai/04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md
 */
class ValidateZoneConfigsCommand extends Command
{
    protected $signature = 'zones:validate-configs
        {--scope= : Filter by scope_type (system|zone|grow_cycle|greenhouse)}
        {--namespace= : Filter by exact namespace, e.g. zone.correction}
        {--json : Output machine-readable JSON instead of human table}';

    protected $description = 'Validate existing automation_config_documents against canonical JSON Schemas';

    public function handle(JsonSchemaValidator $validator): int
    {
        $scope = $this->option('scope');
        $namespaceFilter = $this->option('namespace');
        $asJson = (bool) $this->option('json');

        $supported = $validator->supportedNamespaces();

        $query = DB::table('automation_config_documents')
            ->orderBy('namespace')
            ->orderBy('scope_type')
            ->orderBy('scope_id');

        if ($scope !== null) {
            $query->where('scope_type', $scope);
        }
        if ($namespaceFilter !== null) {
            $query->where('namespace', $namespaceFilter);
        } else {
            $query->whereIn('namespace', $supported);
        }

        $documents = $query->get();

        $report = [];
        $invalidCount = 0;

        foreach ($documents as $doc) {
            if (!in_array($doc->namespace, $supported, true)) {
                continue;
            }

            // Передаём raw JSON string — сохраняет object-vs-array семантику
            // пустых `{}` (при decode→encode через PHP array теряется).
            $payloadJson = is_string($doc->payload) ? $doc->payload : json_encode($doc->payload);

            try {
                $violations = $validator->validate($doc->namespace, $payloadJson, (int) $doc->schema_version);
            } catch (RuntimeException $e) {
                $report[] = [
                    'namespace' => $doc->namespace,
                    'scope_type' => $doc->scope_type,
                    'scope_id' => (int) $doc->scope_id,
                    'violations' => [[
                        'path' => '(root)',
                        'code' => 'schema_error',
                        'message' => $e->getMessage(),
                    ]],
                ];
                $invalidCount++;
                continue;
            }

            if (!empty($violations)) {
                $report[] = [
                    'namespace' => $doc->namespace,
                    'scope_type' => $doc->scope_type,
                    'scope_id' => (int) $doc->scope_id,
                    'violations' => $violations,
                ];
                $invalidCount++;
            }
        }

        if ($asJson) {
            $this->line(json_encode([
                'total_checked' => count($documents),
                'invalid_count' => $invalidCount,
                'documents' => $report,
            ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
        } else {
            $this->renderHumanTable($report, count($documents), $invalidCount);
        }

        return $invalidCount === 0 ? self::SUCCESS : self::FAILURE;
    }

    /**
     * @param list<array{namespace:string,scope_type:string,scope_id:int,violations:array}> $report
     */
    private function renderHumanTable(array $report, int $totalChecked, int $invalidCount): void
    {
        if (empty($report)) {
            $this->info("All {$totalChecked} documents valid.");
            return;
        }

        $this->warn("Invalid documents: {$invalidCount} of {$totalChecked}.");
        $this->newLine();

        $rows = [];
        foreach ($report as $item) {
            foreach ($item['violations'] as $v) {
                $rows[] = [
                    $item['namespace'],
                    $item['scope_type'],
                    $item['scope_id'],
                    $v['path'] ?? '(root)',
                    $v['code'] ?? 'invalid',
                    $this->truncate((string) ($v['message'] ?? '')),
                ];
            }
        }

        $this->table(
            ['namespace', 'scope', 'id', 'path', 'code', 'message'],
            $rows,
        );
    }

    private function truncate(string $message, int $max = 80): string
    {
        if (mb_strlen($message) <= $max) {
            return $message;
        }
        return mb_substr($message, 0, $max - 3) . '...';
    }
}
