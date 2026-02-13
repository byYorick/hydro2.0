<?php

namespace Tests\Feature;

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class QueueContractMigrationRollbackTest extends TestCase
{
    use RefreshDatabase;

    public function test_queue_contract_migration_down_restores_guard_constraints(): void
    {
        $migration = require database_path('migrations/2026_02_11_041506_add_queue_contract_checks.php');
        $this->assertInstanceOf(Migration::class, $migration);

        $migration->down();

        DB::table('pending_status_updates')->insert([
            'cmd_id' => 'rollback-accepted',
            'status' => 'ACCEPTED',
            'details' => json_encode(['test' => true]),
            'retry_count' => 0,
            'max_attempts' => 10,
            'next_retry_at' => now(),
        ]);
        $this->assertDatabaseHas('pending_status_updates', [
            'cmd_id' => 'rollback-accepted',
            'status' => 'ACCEPTED',
        ]);

        $this->assertInsertFailsWithCheckConstraint(function (): void {
            DB::table('pending_status_updates')->insert([
                'cmd_id' => 'rollback-invalid',
                'status' => 'BROKEN',
                'details' => json_encode(['test' => true]),
                'retry_count' => 0,
                'max_attempts' => 10,
                'next_retry_at' => now(),
            ]);
        });

        $this->assertInsertFailsWithCheckConstraint(function (): void {
            DB::table('pending_status_updates_dlq')->insert([
                'cmd_id' => 'rollback-dlq-invalid',
                'status' => 'BROKEN',
                'details' => json_encode(['test' => true]),
                'retry_count' => 1,
                'max_attempts' => 10,
                'last_error' => 'rollback test',
            ]);
        });

        $this->assertInsertFailsWithCheckConstraint(function (): void {
            DB::table('pending_alerts')->insert([
                'zone_id' => null,
                'source' => 'BROKEN',
                'code' => 'ROLLBACK_TEST',
                'type' => 'infra_test',
                'status' => 'ACTIVE',
                'details' => json_encode(['test' => true]),
                'attempts' => 0,
                'max_attempts' => 10,
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        });
    }

    private function assertInsertFailsWithCheckConstraint(callable $callback): void
    {
        try {
            DB::transaction(function () use ($callback): void {
                $callback();
            });
            $this->fail('Expected insert to fail due to check constraint.');
        } catch (QueryException $exception) {
            $this->assertStringContainsString('check', strtolower($exception->getMessage()));
        }
    }
}
