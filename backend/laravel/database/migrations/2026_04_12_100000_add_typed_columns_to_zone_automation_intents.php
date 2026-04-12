<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * AE3 canonicalization: replace JSONB payload with typed columns.
 *
 * Laravel writes task_type / topology / irrigation_mode / irrigation_requested_duration_sec /
 * intent_source directly; payload is no longer written or read.
 * payload column is left nullable for schema rollback safety (no data loss on enqueued rows).
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('zone_automation_intents', function (Blueprint $table) {
            // AE3 canonical task type: cycle_start | irrigation_start | lighting_tick
            $table->string('task_type', 64)->default('cycle_start')->after('intent_type');

            // Execution topology: two_tank | two_tank_drip_substrate_trays | lighting_tick
            $table->string('topology', 64)->default('two_tank')->after('task_type');

            // Irrigation mode: normal | force — NULL for non-irrigation tasks
            $table->string('irrigation_mode', 32)->nullable()->after('topology');

            // Requested irrigation duration in seconds — NULL when not specified
            $table->unsignedInteger('irrigation_requested_duration_sec')->nullable()->after('irrigation_mode');

            // Originating system: laravel_scheduler | api | cron | laravel_grow_cycle_start
            $table->string('intent_source', 64)->nullable()->after('irrigation_requested_duration_sec');
        });
    }

    public function down(): void
    {
        Schema::table('zone_automation_intents', function (Blueprint $table) {
            $table->dropColumn([
                'task_type',
                'topology',
                'irrigation_mode',
                'irrigation_requested_duration_sec',
                'intent_source',
            ]);
        });
    }
};
