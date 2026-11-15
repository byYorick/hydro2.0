<?php

namespace App\Console\Commands;

use App\Support\Database\RuntimeRoleGrants;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class CheckRuntimeDatabaseRoles extends Command
{
    protected $signature = 'hydro:db-runtime-roles {--check : Fail if capability roles are missing or unsafe} {--apply : Reapply managed capability grants after restore and verify them}';

    protected $description = 'List database-scoped runtime capability roles and verify grants, or explicitly reapply capabilities after restore';

    public function handle(): int
    {
        if (DB::getDriverName() !== 'pgsql') {
            $this->error('Runtime capability roles require PostgreSQL.');

            return self::FAILURE;
        }
        if ($this->option('apply')) {
            try {
                DB::transaction(fn () => RuntimeRoleGrants::apply());
            } catch (\Throwable) {
                $this->error('Unable to apply managed runtime roles: check migrator privileges and existing role attributes.');

                return self::FAILURE;
            }
        }
        $failed = false;
        foreach (RuntimeRoleGrants::PROFILES as $profile => $_) {
            $role = RuntimeRoleGrants::role(DB::getDatabaseName(), $profile);
            $this->line($profile.': '.$role.' (capability role, NOLOGIN)');
            if (! $this->option('check') && ! $this->option('apply')) {
                continue;
            }
            $row = DB::selectOne('SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid) AS inherits_roles FROM pg_roles r WHERE rolname = ?', [$role]);
            if (! $row || array_filter((array) $row)) {
                $this->error($profile.': missing or unsafe role attributes');
                $failed = true;

                continue;
            }
            foreach (RuntimeRoleGrants::permissions($profile) as $table => $privileges) {
                if (! Schema::hasTable($table)) {
                    continue;
                }
                foreach ($privileges as $privilege) {
                    $grant = DB::selectOne('SELECT has_table_privilege(?, ?, ?) AS allowed', [$role, 'public.'.$table, $privilege]);
                    if (! $grant->allowed) {
                        $this->error($profile.': missing '.$privilege.' on '.$table);
                        $failed = true;
                    }
                }
            }
            foreach (['users', 'personal_access_tokens', 'recipes', 'migrations'] as $table) {
                if (! Schema::hasTable($table)) {
                    continue;
                }
                $grant = DB::selectOne("SELECT has_table_privilege(?, ?, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS allowed", [$role, 'public.'.$table]);
                if ($grant->allowed) {
                    $this->error($profile.': unexpected privilege on '.$table);
                    $failed = true;
                }
            }
            $schema = DB::selectOne("SELECT has_schema_privilege(?, 'public', 'CREATE') AS allowed", [$role]);
            if ($schema->allowed) {
                $this->error($profile.': unexpected schema CREATE privilege');
                $failed = true;
            }
        }

        return $failed ? self::FAILURE : self::SUCCESS;
    }
}
