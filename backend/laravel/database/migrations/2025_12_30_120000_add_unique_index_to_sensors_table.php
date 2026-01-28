<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('sensors')) {
            return;
        }

        DB::statement(
            'CREATE UNIQUE INDEX IF NOT EXISTS sensors_identity_unique_idx '.
            'ON sensors (zone_id, node_id, scope, type, label)'
        );
    }

    public function down(): void
    {
        if (! Schema::hasTable('sensors')) {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS sensors_identity_unique_idx');
    }
};
