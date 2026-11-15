<?php

namespace Tests\Unit;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Mockery;
use Tests\TestCase;

class RuntimeRoleCommandTest extends TestCase
{
    public function test_check_fails_when_roles_do_not_exist(): void
    {
        DB::shouldReceive('getDriverName')->andReturn('pgsql');
        DB::shouldReceive('getDatabaseName')->andReturn('hydro');
        DB::shouldReceive('selectOne')->andReturn(null);
        $this->artisan('hydro:db-runtime-roles', ['--check' => true])->assertExitCode(1);
    }

    public function test_check_accepts_expected_capabilities(): void
    {
        Schema::swap(Mockery::mock());
        Schema::shouldReceive('hasTable')->andReturn(true);
        DB::shouldReceive('getDriverName')->andReturn('pgsql');
        DB::shouldReceive('getDatabaseName')->andReturn('hydro');
        DB::shouldReceive('selectOne')->andReturnUsing(function ($sql, $params) {
            if (str_contains($sql, 'FROM pg_roles')) {
                return (object) ['rolcanlogin' => false, 'rolsuper' => false, 'rolcreatedb' => false, 'rolcreaterole' => false, 'rolreplication' => false, 'rolbypassrls' => false];
            }

            return (object) ['allowed' => count($params) === 3];
        });
        $this->artisan('hydro:db-runtime-roles', ['--check' => true])->assertExitCode(0);
    }

    public function test_check_rejects_capability_role_with_inherited_memberships(): void
    {
        DB::shouldReceive('getDriverName')->andReturn('pgsql');
        DB::shouldReceive('getDatabaseName')->andReturn('hydro');
        DB::shouldReceive('selectOne')->andReturn((object) ['inherits_roles' => true]);
        $this->artisan('hydro:db-runtime-roles', ['--check' => true])->assertExitCode(1);
    }

    public function test_migration_refuses_unknown_existing_role(): void
    {
        DB::shouldReceive('getDriverName')->andReturn('pgsql');
        DB::shouldReceive('getDatabaseName')->andReturn('hydro');
        DB::shouldReceive('selectOne')->andReturn((object) ['marker' => 'unmanaged']);
        $migration = require database_path('migrations/2026_11_14_100000_create_runtime_capability_roles.php');
        $this->expectException(\RuntimeException::class);
        $migration->up();
    }
}
