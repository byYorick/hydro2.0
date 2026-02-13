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

        if (Schema::hasColumn('pending_alerts', 'next_retry_at')) {
            DB::statement('CREATE INDEX IF NOT EXISTS pending_alerts_next_retry_at_idx ON pending_alerts (next_retry_at)');
            return;
        }

        Schema::table('pending_alerts', function (Blueprint $table) {
            $table->timestampTz('next_retry_at')->nullable()->after('max_attempts');
        });

        DB::statement('CREATE INDEX IF NOT EXISTS pending_alerts_next_retry_at_idx ON pending_alerts (next_retry_at)');
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (! Schema::hasTable('pending_alerts')) {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS pending_alerts_next_retry_at_idx');

        if (! Schema::hasColumn('pending_alerts', 'next_retry_at')) {
            return;
        }

        Schema::table('pending_alerts', function (Blueprint $table) {
            $table->dropColumn('next_retry_at');
        });
    }
};
