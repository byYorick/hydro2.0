<?php

namespace Tests\Unit;

use App\Support\Database\RuntimeRoleGrants;
use PHPUnit\Framework\TestCase;

class RuntimeRoleGrantsTest extends TestCase
{
    public function test_profiles_separate_configuration_telemetry_and_execution(): void
    {
        $hl = RuntimeRoleGrants::permissions('hl');
        $ae = RuntimeRoleGrants::permissions('ae');
        $aggregator = RuntimeRoleGrants::permissions('aggregator');
        $this->assertContains('INSERT', $hl['commands']);
        $this->assertNotContains('INSERT', $ae['commands']);
        $this->assertContains('UPDATE', $ae['ae_tasks']);
        $this->assertArrayNotHasKey('ae_tasks', $hl);
        $this->assertContains('DELETE', $aggregator['telemetry_samples']);
        $this->assertNotContains('UPDATE', $aggregator['telemetry_samples']);
        foreach (array_keys(RuntimeRoleGrants::PROFILES) as $profile) {
            $permissions = RuntimeRoleGrants::permissions($profile);
            foreach (['users', 'personal_access_tokens', 'recipes', 'migrations'] as $table) {
                $this->assertArrayNotHasKey($table, $permissions);
            }
        }
    }

    public function test_role_names_are_database_scoped_and_valid_identifiers(): void
    {
        $a = RuntimeRoleGrants::role('hydro', 'ae');
        $this->assertNotSame($a, RuntimeRoleGrants::role('hydro_test', 'ae'));
        $this->assertMatchesRegularExpression('/^[a-z0-9_]{1,63}$/', RuntimeRoleGrants::role('db"unsafe', 'ae'));
        $this->expectException(\InvalidArgumentException::class);
        RuntimeRoleGrants::role('hydro', 'unknown');
    }
}
