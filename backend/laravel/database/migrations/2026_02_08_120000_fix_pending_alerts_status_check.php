<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('pending_alerts')) {
            return;
        }

        DB::statement('ALTER TABLE pending_alerts DROP CONSTRAINT IF EXISTS pending_alerts_status_check');
        DB::statement("
            ALTER TABLE pending_alerts
            ADD CONSTRAINT pending_alerts_status_check
            CHECK (status IN ('pending', 'failed', 'dlq', 'ACTIVE', 'RESOLVED'))
        ");
    }

    public function down(): void
    {
        if (! Schema::hasTable('pending_alerts')) {
            return;
        }

        DB::statement('ALTER TABLE pending_alerts DROP CONSTRAINT IF EXISTS pending_alerts_status_check');
    }
};

