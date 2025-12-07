<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        // Индекс по coalesce(context->>'service', context->>'source') для фильтрации /api/logs/service
        DB::statement("
            CREATE INDEX IF NOT EXISTS system_logs_service_idx
            ON system_logs ((COALESCE(context->>'service', context->>'source', 'system')))
        ");
    }

    public function down(): void
    {
        DB::statement('DROP INDEX IF EXISTS system_logs_service_idx');
    }
};
