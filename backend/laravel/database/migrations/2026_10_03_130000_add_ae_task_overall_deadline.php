<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        if (! Schema::hasColumn('ae_tasks', 'overall_deadline_at')) {
            Schema::table('ae_tasks', function (Blueprint $table): void {
                $table->timestampTz('overall_deadline_at')->nullable();
            });
        }

        DB::statement(<<<'SQL'
            UPDATE ae_tasks
            SET overall_deadline_at = COALESCE(claimed_at, created_at) + INTERVAL '7 days'
            WHERE overall_deadline_at IS NULL
              AND status IN ('claimed', 'running', 'waiting_command')
            SQL);

        DB::statement(<<<'SQL'
            UPDATE ae_tasks
            SET overall_deadline_at = created_at + INTERVAL '7 days'
            WHERE overall_deadline_at IS NULL
              AND status = 'pending'
              AND claim_generation > 0
            SQL);

        DB::statement(<<<'SQL'
            CREATE INDEX IF NOT EXISTS ae_tasks_overall_deadline_idx
            ON ae_tasks (overall_deadline_at)
            WHERE overall_deadline_at IS NOT NULL
              AND status IN ('pending', 'claimed', 'running', 'waiting_command')
            SQL);
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS ae_tasks_overall_deadline_idx');

        if (Schema::hasColumn('ae_tasks', 'overall_deadline_at')) {
            Schema::table('ae_tasks', function (Blueprint $table): void {
                $table->dropColumn('overall_deadline_at');
            });
        }
    }
};
