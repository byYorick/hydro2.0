<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        foreach (['pending_status_updates', 'pending_status_updates_dlq'] as $table) {
            if (Schema::hasTable($table) && Schema::hasColumn($table, 'cmd_id')) {
                DB::statement("ALTER TABLE {$table} ALTER COLUMN cmd_id TYPE VARCHAR(128)");
            }
        }
    }

    public function down(): void
    {
        foreach (['pending_status_updates', 'pending_status_updates_dlq'] as $table) {
            if (! Schema::hasTable($table) || ! Schema::hasColumn($table, 'cmd_id')) {
                continue;
            }

            $hasOversizedIds = DB::table($table)
                ->whereRaw('char_length(cmd_id) > 64')
                ->exists();

            if ($hasOversizedIds) {
                throw new RuntimeException(
                    "Cannot shrink {$table}.cmd_id to 64 characters while longer command IDs exist."
                );
            }

            DB::statement("ALTER TABLE {$table} ALTER COLUMN cmd_id TYPE VARCHAR(64)");
        }
    }
};
