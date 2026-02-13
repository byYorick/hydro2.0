<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        if (Schema::hasTable('pending_alerts')) {
            DB::statement("
                UPDATE pending_alerts
                SET source = CASE
                    WHEN source IS NULL THEN 'infra'
                    WHEN lower(source) IN ('biz', 'infra', 'node') THEN lower(source)
                    ELSE 'infra'
                END
            ");

            DB::statement('ALTER TABLE pending_alerts DROP CONSTRAINT IF EXISTS pending_alerts_source_check');
            DB::statement("
                ALTER TABLE pending_alerts
                ADD CONSTRAINT pending_alerts_source_check
                CHECK (source IN ('biz', 'infra', 'node'))
            ");
        }

        if (Schema::hasTable('pending_status_updates')) {
            DB::statement("
                UPDATE pending_status_updates
                SET status = CASE
                    WHEN upper(status) = 'SENT' THEN 'SENT'
                    WHEN upper(status) = 'ACK' THEN 'ACK'
                    WHEN upper(status) = 'DONE' THEN 'DONE'
                    WHEN upper(status) = 'ERROR' THEN 'ERROR'
                    WHEN upper(status) = 'INVALID' THEN 'INVALID'
                    WHEN upper(status) = 'BUSY' THEN 'BUSY'
                    WHEN upper(status) = 'NO_EFFECT' THEN 'NO_EFFECT'
                    WHEN upper(status) = 'ACCEPTED' THEN 'ACK'
                    ELSE 'ERROR'
                END
            ");

            DB::statement('ALTER TABLE pending_status_updates DROP CONSTRAINT IF EXISTS pending_status_updates_status_check');
            DB::statement("
                ALTER TABLE pending_status_updates
                ADD CONSTRAINT pending_status_updates_status_check
                CHECK (status IN ('SENT', 'ACK', 'DONE', 'ERROR', 'INVALID', 'BUSY', 'NO_EFFECT'))
            ");
        }

        if (Schema::hasTable('pending_status_updates_dlq')) {
            DB::statement("
                UPDATE pending_status_updates_dlq
                SET status = CASE
                    WHEN upper(status) = 'SENT' THEN 'SENT'
                    WHEN upper(status) = 'ACK' THEN 'ACK'
                    WHEN upper(status) = 'DONE' THEN 'DONE'
                    WHEN upper(status) = 'ERROR' THEN 'ERROR'
                    WHEN upper(status) = 'INVALID' THEN 'INVALID'
                    WHEN upper(status) = 'BUSY' THEN 'BUSY'
                    WHEN upper(status) = 'NO_EFFECT' THEN 'NO_EFFECT'
                    WHEN upper(status) = 'ACCEPTED' THEN 'ACK'
                    ELSE 'ERROR'
                END
            ");

            DB::statement('ALTER TABLE pending_status_updates_dlq DROP CONSTRAINT IF EXISTS pending_status_updates_dlq_status_check');
            DB::statement("
                ALTER TABLE pending_status_updates_dlq
                ADD CONSTRAINT pending_status_updates_dlq_status_check
                CHECK (status IN ('SENT', 'ACK', 'DONE', 'ERROR', 'INVALID', 'BUSY', 'NO_EFFECT'))
            ");
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (Schema::hasTable('pending_alerts')) {
            DB::statement('ALTER TABLE pending_alerts DROP CONSTRAINT IF EXISTS pending_alerts_source_check');
            DB::statement("
                ALTER TABLE pending_alerts
                ADD CONSTRAINT pending_alerts_source_check
                CHECK (source IN ('biz', 'infra', 'node'))
            ");
        }

        if (Schema::hasTable('pending_status_updates')) {
            DB::statement('ALTER TABLE pending_status_updates DROP CONSTRAINT IF EXISTS pending_status_updates_status_check');
            DB::statement("
                ALTER TABLE pending_status_updates
                ADD CONSTRAINT pending_status_updates_status_check
                CHECK (status IN ('SENT', 'ACK', 'DONE', 'ERROR', 'INVALID', 'BUSY', 'NO_EFFECT', 'ACCEPTED'))
            ");
        }

        if (Schema::hasTable('pending_status_updates_dlq')) {
            DB::statement('ALTER TABLE pending_status_updates_dlq DROP CONSTRAINT IF EXISTS pending_status_updates_dlq_status_check');
            DB::statement("
                ALTER TABLE pending_status_updates_dlq
                ADD CONSTRAINT pending_status_updates_dlq_status_check
                CHECK (status IN ('SENT', 'ACK', 'DONE', 'ERROR', 'INVALID', 'BUSY', 'NO_EFFECT', 'ACCEPTED'))
            ");
        }
    }
};
