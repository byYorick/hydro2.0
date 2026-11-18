<?php

use App\Support\Database\RuntimeRoleGrants;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    private const BUCKETS = ['telemetry_agg_1m' => 'ts', 'telemetry_agg_1h' => 'ts', 'telemetry_daily' => 'date'];

    public function up(): void
    {
        foreach (self::BUCKETS as $table => $bucket) {
            $keys = "zone_id, node_id, channel, metric_type, {$bucket}";
            $nullable = 'zone_id IS NULL OR node_id IS NULL OR channel IS NULL';
            // PostgreSQL normally treats NULL keys as distinct. Keep the latest
            // snapshot per group and serialize the repair with aggregate writers.
            DB::statement("LOCK TABLE {$table} IN SHARE ROW EXCLUSIVE MODE");
            DB::statement("DELETE FROM {$table} target USING (
                SELECT id, {$bucket}, row_number() OVER (PARTITION BY {$keys} ORDER BY id DESC) AS position
                FROM {$table} WHERE {$nullable}
            ) ranked WHERE ranked.position > 1 AND target.id = ranked.id AND target.{$bucket} = ranked.{$bucket}");
            DB::statement("CREATE UNIQUE INDEX {$table}_nullable_key
                ON {$table} ({$keys}) NULLS NOT DISTINCT WHERE {$nullable}");
        }
        RuntimeRoleGrants::apply();
    }

    public function down(): void
    {
        foreach (self::BUCKETS as $table => $_) {
            DB::statement("DROP INDEX {$table}_nullable_key");
        }
        $role = RuntimeRoleGrants::role(DB::getDatabaseName(), 'aggregator');
        DB::statement('REVOKE SELECT ON sensors, zone_simulations FROM "'.$role.'"');
        DB::statement('REVOKE INSERT ON simulation_events FROM "'.$role.'"');
        DB::statement('REVOKE USAGE, SELECT ON SEQUENCE simulation_events_id_seq FROM "'.$role.'"');
    }
};
