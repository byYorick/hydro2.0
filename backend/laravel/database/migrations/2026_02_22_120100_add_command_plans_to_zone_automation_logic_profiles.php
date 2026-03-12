<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('zone_automation_logic_profiles')) {
            return;
        }

        if (! Schema::hasColumn('zone_automation_logic_profiles', 'command_plans')) {
            Schema::table('zone_automation_logic_profiles', function (Blueprint $table) {
                $table->jsonb('command_plans')->default(DB::raw("'{}'::jsonb"))->after('subsystems');
            });
        }

        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement(
            "
            UPDATE zone_automation_logic_profiles
            SET command_plans = jsonb_build_object(
                'schema_version', 1,
                'plan_version', 1,
                'source', 'subsystems_backfill',
                'plans', jsonb_build_object(
                    'diagnostics', jsonb_build_object(
                        'execution', COALESCE((subsystems #> '{diagnostics,execution}')::jsonb, '{}'::jsonb),
                        'two_tank_commands', COALESCE((subsystems #> '{diagnostics,execution,two_tank_commands}')::jsonb, '{}'::jsonb),
                        'steps', COALESCE((subsystems #> '{diagnostics,execution,two_tank_commands,steps}')::jsonb, '[]'::jsonb)
                    )
                )
            )
            WHERE command_plans IS NULL OR command_plans = '{}'::jsonb
            "
        );
    }

    public function down(): void
    {
        if (! Schema::hasTable('zone_automation_logic_profiles')) {
            return;
        }

        if (Schema::hasColumn('zone_automation_logic_profiles', 'command_plans')) {
            Schema::table('zone_automation_logic_profiles', function (Blueprint $table) {
                $table->dropColumn('command_plans');
            });
        }
    }
};
