<?php

namespace Tests\Feature;

use App\Models\User;
use Database\Seeders\AdminUserSeeder;
use Database\Seeders\StartUsersSeeder;
use Illuminate\Support\Facades\Hash;
use Tests\RefreshDatabase;
use Tests\TestCase;

class StartUsersSeederTest extends TestCase
{
    use RefreshDatabase;

    public function test_start_users_seeder_creates_all_base_roles_with_deterministic_credentials(): void
    {
        $this->seed(StartUsersSeeder::class);

        $this->assertSeededBaseUsers();
    }

    public function test_admin_user_seeder_creates_all_base_roles_with_deterministic_credentials(): void
    {
        $this->seed(AdminUserSeeder::class);

        $this->assertSeededBaseUsers();
    }

    private function assertSeededBaseUsers(): void
    {
        $expectedUsers = [
            'admin@example.com' => 'admin',
            'agronomist@example.com' => 'agronomist',
            'operator@example.com' => 'operator',
            'viewer@example.com' => 'viewer',
            'engineer@example.com' => 'engineer',
        ];

        foreach ($expectedUsers as $email => $role) {
            $user = User::query()->where('email', $email)->first();

            $this->assertNotNull($user, "User {$email} was not seeded.");
            $this->assertSame($role, $user->role);
            $this->assertTrue(Hash::check('password', $user->password));
        }
    }
}
