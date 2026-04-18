<?php

declare(strict_types=1);

namespace Tests\Feature\Contract;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

/**
 * Снимает snapshot схемы БД для таблиц, на которые опирается AE3 (automation-engine).
 *
 * Laravel — владелец миграций; AE3 читает схему напрямую через asyncpg.
 * Этот тест защищает скрытый контракт: если миграция уронила/переименовала колонку,
 * от которой зависит AE3, snapshot разойдётся с committed и тест упадёт.
 *
 * Список таблиц-кандидатов дублирует {@see backend/services/automation-engine/ae3lite/infrastructure/read_models/laravel_schema_contract.py::ALL_TABLES}.
 * Python-валидатор (test_read_model_contract.py) потом сверяет, что все required-колонки AE3 ⊆ snapshot.
 *
 * Обновить snapshot: UPDATE_SCHEMA_SNAPSHOT=1 php artisan test --filter=AutomationReadModelSchemaTest
 */
class AutomationReadModelSchemaTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Shared-путь к schemas/ монтируется в оба контейнера (laravel и automation-engine)
     * через docker-compose.dev.yml. Python-валидатор читает ТОТ ЖЕ файл.
     *
     * Host-путь: schemas/automation_read_model_schema.json (коммитится в git).
     */
    private const SNAPSHOT_CONTAINER_PATH = '/schemas/automation_read_model_schema.json';
    private const SNAPSHOT_CI_FALLBACK_RELATIVE = 'schemas/automation_read_model_schema.json';

    /**
     * Таблицы, от которых зависит AE3. При добавлении новой зависимости — добавь и сюда,
     * и в laravel_schema_contract.py::ALL_TABLES.
     */
    private const TRACKED_TABLES = [
        'ae_tasks',
        'ae_commands',
        'ae_stage_transitions',
        'ae_zone_leases',
        'pid_state',
        'zone_workflow_state',
        'zone_automation_intents',
        'zones',
        'greenhouses',
        'grow_cycles',
        'grow_cycle_phases',
        'automation_effective_bundles',
        'automation_config_documents',
        'sensors',
        'telemetry_last',
        'telemetry_samples',
        'zone_events',
        'nodes',
        'node_channels',
        'channel_bindings',
        'pump_calibrations',
        'alerts',
        'commands',
        'unassigned_node_errors',
    ];

    public function test_schema_snapshot_matches_committed(): void
    {
        $snapshot = $this->buildSnapshot();
        $path = $this->resolveSnapshotPath();

        if (env('UPDATE_SCHEMA_SNAPSHOT')) {
            @mkdir(dirname($path), 0775, true);
            file_put_contents($path, json_encode(
                $snapshot,
                JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
            )."\n");
            $this->markTestSkipped('Schema snapshot regenerated at '.$path);
        }

        $this->assertFileExists(
            $path,
            'Schema snapshot отсутствует. Сгенерируй: UPDATE_SCHEMA_SNAPSHOT=1 docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=AutomationReadModelSchemaTest'
        );

        $committed = json_decode((string) file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
        unset($committed['generated_at'], $snapshot['generated_at']);

        $this->assertSame(
            $committed,
            $snapshot,
            'Схема БД разошлась с committed snapshot. Если это ожидаемо — регенерируй: '
            .'UPDATE_SCHEMA_SNAPSHOT=1 php artisan test --filter=AutomationReadModelSchemaTest. '
            .'Затем убедись, что laravel_schema_contract.py тоже обновлён под новые колонки/enum.'
        );
    }

    private function resolveSnapshotPath(): string
    {
        if (is_dir('/schemas')) {
            return self::SNAPSHOT_CONTAINER_PATH;
        }

        // CI / host-локальный запуск без docker-compose: путь относительно laravel/.
        return base_path('../../'.self::SNAPSHOT_CI_FALLBACK_RELATIVE);
    }

    /**
     * @return array<string, mixed>
     */
    private function buildSnapshot(): array
    {
        $tables = [];

        $columnRows = DB::select(
            'SELECT table_name, column_name, data_type, udt_name, is_nullable '
            .'FROM information_schema.columns '
            .'WHERE table_schema = current_schema() AND table_name = ANY(?::text[]) '
            .'ORDER BY table_name, ordinal_position',
            ['{'.implode(',', self::TRACKED_TABLES).'}']
        );

        foreach ($columnRows as $row) {
            $tables[$row->table_name]['columns'][$row->column_name] = [
                'data_type' => $row->data_type,
                'udt_name' => $row->udt_name,
                'is_nullable' => $row->is_nullable,
            ];
        }

        foreach (self::TRACKED_TABLES as $name) {
            if (! isset($tables[$name])) {
                $tables[$name] = ['columns' => []]; // missing — явно зафиксируем
            }
        }

        ksort($tables);
        foreach ($tables as &$tbl) {
            ksort($tbl['columns']);
        }
        unset($tbl);

        return [
            'version' => 1,
            'generated_at' => date(DATE_ATOM),
            'tracked_tables_count' => count(self::TRACKED_TABLES),
            'tables' => $tables,
        ];
    }
}
