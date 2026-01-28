<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        if (! Schema::hasTable('pending_alerts')) {
            return;
        }

        if (! Schema::hasColumn('pending_alerts', 'next_retry_at')) {
            Schema::table('pending_alerts', function (Blueprint $table) {
                $table->timestampTz('next_retry_at')->nullable()->after('max_attempts');
            });
        }

        if (! Schema::hasColumn('pending_alerts', 'moved_to_dlq_at')) {
            Schema::table('pending_alerts', function (Blueprint $table) {
                $table->timestampTz('moved_to_dlq_at')->nullable()->after('next_retry_at');
            });
        }

        if (Schema::hasColumn('pending_alerts', 'max_attempts')) {
            DB::statement('ALTER TABLE pending_alerts ALTER COLUMN max_attempts SET DEFAULT 10');
        }

        DB::statement('CREATE INDEX IF NOT EXISTS idx_pending_alerts_zone_id ON pending_alerts(zone_id)');
        DB::statement('CREATE INDEX IF NOT EXISTS idx_pending_alerts_retry ON pending_alerts(next_retry_at) WHERE next_retry_at IS NOT NULL');
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (! Schema::hasTable('pending_alerts')) {
            return;
        }

        if (Schema::hasColumn('pending_alerts', 'moved_to_dlq_at')) {
            Schema::table('pending_alerts', function (Blueprint $table) {
                $table->dropColumn('moved_to_dlq_at');
            });
        }

        if (Schema::hasColumn('pending_alerts', 'max_attempts')) {
            DB::statement('ALTER TABLE pending_alerts ALTER COLUMN max_attempts SET DEFAULT 3');
        }

        DB::statement('DROP INDEX IF EXISTS idx_pending_alerts_zone_id');
        DB::statement('DROP INDEX IF EXISTS idx_pending_alerts_retry');
    }
};
