<?php

namespace App\Support\Database;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use RuntimeException;

/** Explicit runtime capabilities. Roles cannot own schema or manage users. */
final class RuntimeRoleGrants
{
    public const PROFILES = [
        'hl' => [
            'read' => 'ae_zone_leases commands greenhouses grow_cycle_phases grow_cycles node_channels nodes sensor_calibrations sensors telemetry_last telemetry_samples zones zone_simulations alerts zone_events pending_alerts pending_alerts_dlq pending_status_updates pending_status_updates_dlq unassigned_node_errors',
            'write' => 'commands node_channels nodes sensor_calibrations sensors telemetry_last telemetry_samples simulation_events ai_logs zone_events pending_alerts pending_alerts_dlq pending_status_updates pending_status_updates_dlq unassigned_node_errors',
        ],
        'ae' => [
            'read' => 'ae_commands ae_stage_transitions ae_tasks ae_zone_leases alerts automation_config_documents automation_effective_bundles channel_bindings commands greenhouse_automation_intents greenhouse_automation_leases greenhouse_automation_state greenhouse_automation_tasks greenhouse_manual_overrides greenhouses grow_cycle_phases grow_cycles infrastructure_instances node_channels nodes pid_state pump_calibrations sensors telemetry_last telemetry_samples zone_automation_intents zone_events zone_prepare_baselines zone_workflow_state zones pending_alerts pending_alerts_dlq',
            'write' => 'ae_commands ae_stage_transitions ae_tasks ae_zone_leases greenhouse_automation_intents greenhouse_automation_leases greenhouse_automation_state greenhouse_automation_tasks pid_state zone_automation_intents zone_prepare_baselines zone_workflow_state zone_events pending_alerts pending_alerts_dlq',
            'update' => 'automation_config_documents zones',
        ],
        'bridge' => ['read' => 'pending_alerts pending_alerts_dlq zone_events', 'write' => 'pending_alerts pending_alerts_dlq zone_events'],
        'aggregator' => [
            'read' => 'sensors zone_simulations aggregator_state telemetry_agg_1h telemetry_agg_1m telemetry_daily telemetry_samples',
            'write' => 'aggregator_state telemetry_agg_1h telemetry_agg_1m telemetry_daily pending_alerts pending_alerts_dlq zone_events',
            'insert' => 'simulation_events',
            'delete' => 'telemetry_samples',
        ],
    ];

    public static function role(string $database, string $profile): string
    {
        if (! array_key_exists($profile, self::PROFILES)) {
            throw new \InvalidArgumentException('Unknown database runtime profile');
        }

        return 'hydro_'.substr(hash('sha256', $database), 0, 12).'_'.$profile;
    }

    /** @return array<string, list<string>> */
    public static function permissions(string $profile): array
    {
        $config = self::PROFILES[$profile];
        $permissions = [];
        foreach (['read' => ['SELECT'], 'write' => ['SELECT', 'INSERT', 'UPDATE', 'DELETE'], 'insert' => ['INSERT'], 'update' => ['UPDATE'], 'delete' => ['DELETE']] as $key => $privileges) {
            foreach (array_filter(explode(' ', $config[$key] ?? '')) as $table) {
                $permissions[$table] = array_values(array_unique(array_merge($permissions[$table] ?? [], $privileges)));
            }
        }

        return $permissions;
    }

    public static function apply(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }
        $database = DB::getDatabaseName();
        foreach (self::PROFILES as $profile => $_) {
            $role = self::role($database, $profile);
            // Never reuse a pre-existing role with unknown privileges.
            if (! DB::selectOne('SELECT 1 FROM pg_roles WHERE rolname = ?', [$role])) {
                DB::statement('CREATE ROLE "'.$role.'" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS');
                DB::statement('COMMENT ON ROLE "'.$role.'" IS $$Hydro managed runtime capability role$$');
            } else {
                $existing = DB::selectOne("SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid) AS inherits_roles, shobj_description(oid, 'pg_authid') AS marker FROM pg_roles r WHERE rolname = ?", [$role]);
                if ($existing->marker !== 'Hydro managed runtime capability role' || $existing->rolcanlogin || $existing->rolsuper || $existing->rolcreatedb || $existing->rolcreaterole || $existing->rolreplication || $existing->rolbypassrls || $existing->inherits_roles) {
                    throw new RuntimeException('Existing runtime role is not a managed capability role');
                }
            }
            DB::statement('GRANT USAGE ON SCHEMA public TO "'.$role.'"');
            foreach (self::permissions($profile) as $table => $permissions) {
                if (! Schema::hasTable($table)) {
                    continue;
                }
                DB::statement('GRANT '.implode(', ', $permissions).' ON TABLE public."'.$table.'" TO "'.$role.'"');
                if (in_array('INSERT', $permissions, true)) {
                    $row = DB::selectOne("SELECT pg_get_serial_sequence(?, a.attname) AS sequence FROM pg_attribute a WHERE a.attrelid = to_regclass(?) AND a.attname = 'id' AND NOT a.attisdropped", ['public.'.$table, 'public.'.$table]);
                    if ($row?->sequence) {
                        // Sequence name comes from PostgreSQL, quote each identifier.
                        $sequence = implode('.', array_map(fn ($part) => '"'.str_replace('"', '""', trim($part, '"')).'"', explode('.', $row->sequence)));
                        DB::statement('GRANT USAGE, SELECT ON SEQUENCE '.$sequence.' TO "'.$role.'"');
                    }
                }
            }
        }
    }

    public static function revoke(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }
        foreach (self::PROFILES as $profile => $_) {
            $role = self::role(DB::getDatabaseName(), $profile);
            // Revoke capabilities without DROP OWNED (which can delete objects).
            DB::statement('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM "'.$role.'"');
            DB::statement('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM "'.$role.'"');
            DB::statement('REVOKE USAGE ON SCHEMA public FROM "'.$role.'"');
        }
    }
}
