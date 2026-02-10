<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('alerts', function (Blueprint $table) {
            if (! Schema::hasColumn('alerts', 'category')) {
                $table->string('category', 32)->nullable()->after('status');
            }
            if (! Schema::hasColumn('alerts', 'severity')) {
                $table->string('severity', 16)->nullable()->after('category');
            }
            if (! Schema::hasColumn('alerts', 'node_uid')) {
                $table->string('node_uid', 100)->nullable()->after('severity');
            }
            if (! Schema::hasColumn('alerts', 'hardware_id')) {
                $table->string('hardware_id', 100)->nullable()->after('node_uid');
            }
            if (! Schema::hasColumn('alerts', 'first_seen_at')) {
                $table->timestamp('first_seen_at')->nullable()->after('error_count');
            }
            if (! Schema::hasColumn('alerts', 'last_seen_at')) {
                $table->timestamp('last_seen_at')->nullable()->after('first_seen_at');
            }
        });

        if (DB::getDriverName() === 'pgsql') {
            DB::statement("UPDATE alerts SET category = COALESCE(category, CASE WHEN code LIKE 'node_error_%' THEN 'node' WHEN code LIKE 'biz_%' THEN 'agronomy' WHEN code LIKE 'infra_%' THEN 'infrastructure' ELSE 'other' END)");
            DB::statement("UPDATE alerts SET severity = COALESCE(severity, NULLIF(lower(details->>'severity'), ''), NULLIF(lower(details->>'level'), ''), CASE WHEN code LIKE '%timeout%' OR code LIKE '%circuit_open%' OR code LIKE '%db_unreachable%' OR code LIKE '%mqtt_down%' THEN 'critical' WHEN code LIKE '%failed%' OR code LIKE '%error%' THEN 'error' ELSE 'warning' END)");
            DB::statement("UPDATE alerts SET node_uid = COALESCE(node_uid, NULLIF(details->>'node_uid', ''))");
            DB::statement("UPDATE alerts SET hardware_id = COALESCE(hardware_id, NULLIF(details->>'hardware_id', ''))");
            DB::statement("UPDATE alerts SET first_seen_at = COALESCE(first_seen_at, created_at)");
            DB::statement("UPDATE alerts SET last_seen_at = COALESCE(last_seen_at, NULLIF(details->>'last_seen_at','')::timestamp, created_at)");

            DB::statement('CREATE INDEX IF NOT EXISTS alerts_severity_idx ON alerts(severity)');
            DB::statement('CREATE INDEX IF NOT EXISTS alerts_category_idx ON alerts(category)');
            DB::statement('CREATE INDEX IF NOT EXISTS alerts_node_uid_idx ON alerts(node_uid)');
            DB::statement('CREATE INDEX IF NOT EXISTS alerts_hardware_id_idx ON alerts(hardware_id)');
            DB::statement('CREATE INDEX IF NOT EXISTS alerts_zone_status_severity_idx ON alerts(zone_id, status, severity)');
            DB::statement('CREATE INDEX IF NOT EXISTS alerts_zone_status_category_idx ON alerts(zone_id, status, category)');
            DB::statement('CREATE INDEX IF NOT EXISTS alerts_source_code_status_idx ON alerts(source, code, status)');
        } else {
            DB::statement("UPDATE alerts SET category = COALESCE(category, CASE WHEN code LIKE 'node_error_%' THEN 'node' WHEN code LIKE 'biz_%' THEN 'agronomy' WHEN code LIKE 'infra_%' THEN 'infrastructure' ELSE 'other' END)");
            DB::statement("UPDATE alerts SET severity = COALESCE(severity, NULLIF(lower(JSON_UNQUOTE(JSON_EXTRACT(details, '$.severity'))), ''), NULLIF(lower(JSON_UNQUOTE(JSON_EXTRACT(details, '$.level'))), ''), CASE WHEN code LIKE '%timeout%' OR code LIKE '%circuit_open%' OR code LIKE '%db_unreachable%' OR code LIKE '%mqtt_down%' THEN 'critical' WHEN code LIKE '%failed%' OR code LIKE '%error%' THEN 'error' ELSE 'warning' END)");
            DB::statement("UPDATE alerts SET node_uid = COALESCE(node_uid, NULLIF(JSON_UNQUOTE(JSON_EXTRACT(details, '$.node_uid')), ''))");
            DB::statement("UPDATE alerts SET hardware_id = COALESCE(hardware_id, NULLIF(JSON_UNQUOTE(JSON_EXTRACT(details, '$.hardware_id')), ''))");
            DB::statement("UPDATE alerts SET first_seen_at = COALESCE(first_seen_at, created_at)");
            DB::statement("UPDATE alerts SET last_seen_at = COALESCE(last_seen_at, created_at)");

            Schema::table('alerts', function (Blueprint $table) {
                $table->index('severity', 'alerts_severity_idx');
                $table->index('category', 'alerts_category_idx');
                $table->index('node_uid', 'alerts_node_uid_idx');
                $table->index('hardware_id', 'alerts_hardware_id_idx');
                $table->index(['zone_id', 'status', 'severity'], 'alerts_zone_status_severity_idx');
                $table->index(['zone_id', 'status', 'category'], 'alerts_zone_status_category_idx');
                $table->index(['source', 'code', 'status'], 'alerts_source_code_status_idx');
            });
        }
    }

    public function down(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            DB::statement('DROP INDEX IF EXISTS alerts_source_code_status_idx');
            DB::statement('DROP INDEX IF EXISTS alerts_zone_status_category_idx');
            DB::statement('DROP INDEX IF EXISTS alerts_zone_status_severity_idx');
            DB::statement('DROP INDEX IF EXISTS alerts_hardware_id_idx');
            DB::statement('DROP INDEX IF EXISTS alerts_node_uid_idx');
            DB::statement('DROP INDEX IF EXISTS alerts_category_idx');
            DB::statement('DROP INDEX IF EXISTS alerts_severity_idx');
        } else {
            Schema::table('alerts', function (Blueprint $table) {
                $table->dropIndex('alerts_source_code_status_idx');
                $table->dropIndex('alerts_zone_status_category_idx');
                $table->dropIndex('alerts_zone_status_severity_idx');
                $table->dropIndex('alerts_hardware_id_idx');
                $table->dropIndex('alerts_node_uid_idx');
                $table->dropIndex('alerts_category_idx');
                $table->dropIndex('alerts_severity_idx');
            });
        }

        Schema::table('alerts', function (Blueprint $table) {
            if (Schema::hasColumn('alerts', 'last_seen_at')) {
                $table->dropColumn('last_seen_at');
            }
            if (Schema::hasColumn('alerts', 'first_seen_at')) {
                $table->dropColumn('first_seen_at');
            }
            if (Schema::hasColumn('alerts', 'hardware_id')) {
                $table->dropColumn('hardware_id');
            }
            if (Schema::hasColumn('alerts', 'node_uid')) {
                $table->dropColumn('node_uid');
            }
            if (Schema::hasColumn('alerts', 'severity')) {
                $table->dropColumn('severity');
            }
            if (Schema::hasColumn('alerts', 'category')) {
                $table->dropColumn('category');
            }
        });
    }
};
