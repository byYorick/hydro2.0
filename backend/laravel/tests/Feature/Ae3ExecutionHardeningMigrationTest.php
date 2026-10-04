<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Tests\TestCase;

class Ae3ExecutionHardeningMigrationTest extends TestCase
{
    public function test_only_hardening_migrations_rollback_and_reapply(): void
    {
        $this->assertSame('hydro_test', DB::connection()->getDatabaseName());
        $paths = [
            '2026_10_03_120000_add_ae_claim_generation.php',
            '2026_10_03_130000_add_ae_task_overall_deadline.php',
            '2026_10_03_140000_create_ae_claim_generation_sequence.php',
        ];
        $migrations = array_map(fn ($path) => require database_path('migrations/'.$path), $paths);
        DB::beginTransaction();
        try {
            foreach (array_reverse($migrations) as $migration) {
                $migration->down();
            }
            $this->assertFalse(Schema::hasColumn('ae_tasks', 'claim_generation'));
            $this->assertFalse(Schema::hasColumn('ae_tasks', 'overall_deadline_at'));
            foreach ($migrations as $migration) {
                $migration->up();
            }
            $this->assertTrue(Schema::hasColumn('ae_tasks', 'claim_generation'));
            $this->assertTrue(Schema::hasColumn('ae_zone_leases', 'process_run_id'));
            $this->assertTrue(Schema::hasColumn('ae_tasks', 'overall_deadline_at'));
            $first = DB::selectOne("SELECT nextval('ae_claim_generation_seq') AS value")->value;
            $second = DB::selectOne("SELECT nextval('ae_claim_generation_seq') AS value")->value;
            $this->assertGreaterThan($first, $second);
        } finally {
            DB::rollBack();
        }
    }
}
