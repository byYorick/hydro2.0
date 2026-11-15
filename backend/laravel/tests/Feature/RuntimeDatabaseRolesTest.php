<?php

namespace Tests\Feature;

use App\Support\Database\RuntimeRoleGrants;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class RuntimeDatabaseRolesTest extends TestCase
{
    use RefreshDatabase;

    private function allowed(string $profile, string $table, string $privilege): bool
    {
        return DB::selectOne('SELECT has_table_privilege(?, ?, ?) AS allowed', [
            RuntimeRoleGrants::role(DB::getDatabaseName(), $profile), 'public.'.$table, $privilege,
        ])->allowed;
    }

    public function test_runtime_services_have_separate_write_capabilities(): void
    {
        $this->assertTrue($this->allowed('hl', 'commands', 'INSERT'));
        $this->assertFalse($this->allowed('ae', 'commands', 'INSERT'));
        $this->assertTrue($this->allowed('ae', 'ae_tasks', 'UPDATE'));
        $this->assertFalse($this->allowed('hl', 'ae_tasks', 'UPDATE'));
        $this->assertTrue($this->allowed('aggregator', 'telemetry_samples', 'DELETE'));
        $this->assertFalse($this->allowed('aggregator', 'telemetry_samples', 'UPDATE'));
        foreach (array_keys(RuntimeRoleGrants::PROFILES) as $profile) {
            $this->assertFalse($this->allowed($profile, 'users', 'SELECT,INSERT,UPDATE,DELETE'));
            $role = RuntimeRoleGrants::role(DB::getDatabaseName(), $profile);
            $this->assertFalse(DB::selectOne("SELECT has_schema_privilege(?, 'public', 'CREATE') AS allowed", [$role])->allowed);
        }
    }

    public function test_history_logger_can_use_command_sequence(): void
    {
        $role = RuntimeRoleGrants::role(DB::getDatabaseName(), 'hl');
        $row = DB::selectOne("SELECT has_sequence_privilege(?, pg_get_serial_sequence('public.commands', 'id'), 'USAGE') AS allowed", [$role]);
        $this->assertTrue($row->allowed);
    }

    public function test_rollback_revokes_runtime_capabilities(): void
    {
        $before = DB::table('commands')->count();
        $migration = require database_path('migrations/2026_11_14_100000_create_runtime_capability_roles.php');
        $migration->down();
        $this->assertFalse($this->allowed('hl', 'commands', 'INSERT'));
        $this->assertFalse($this->allowed('ae', 'ae_tasks', 'UPDATE'));
        $this->assertSame($before, DB::table('commands')->count());
    }

    public function test_explicit_apply_restores_grants_after_rollback(): void
    {
        RuntimeRoleGrants::revoke();
        $this->assertFalse($this->allowed('hl', 'commands', 'INSERT'));
        $this->artisan('hydro:db-runtime-roles', ['--apply' => true])->assertExitCode(0);
        $this->assertTrue($this->allowed('hl', 'commands', 'INSERT'));
        $this->assertFalse($this->allowed('ae', 'commands', 'INSERT'));
        $this->assertFalse($this->allowed('hl', 'users', 'SELECT'));
    }
}
