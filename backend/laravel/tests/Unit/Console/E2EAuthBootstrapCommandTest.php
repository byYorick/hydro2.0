<?php

namespace Tests\Unit\Console;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Hash;
use Tests\TestCase;

class E2EAuthBootstrapCommandTest extends TestCase
{
    public function test_command_signature_exists(): void
    {
        $commands = Artisan::all();
        $this->assertArrayHasKey('e2e:auth-bootstrap', $commands);
    }

    public function test_creates_user_if_not_exists(): void
    {
        // Удаляем пользователя если существует
        User::where('email', 'e2e@test.local')->delete();

        $this->assertDatabaseMissing('users', ['email' => 'e2e@test.local']);

        Artisan::call('e2e:auth-bootstrap');

        $this->assertDatabaseHas('users', [
            'email' => 'e2e@test.local',
            'role' => 'admin',
        ]);
    }

    public function test_uses_existing_user_if_exists(): void
    {
        $user = User::firstOrCreate(
            ['email' => 'e2e@test.local'],
            [
                'name' => 'E2E Test User',
                'password' => Hash::make('test'),
                'role' => 'viewer',
            ]
        );

        $originalId = $user->id;

        Artisan::call('e2e:auth-bootstrap', ['--role' => 'admin']);

        $user->refresh();
        $this->assertEquals($originalId, $user->id);
        $this->assertEquals('admin', $user->role);
    }

    public function test_outputs_token(): void
    {
        Artisan::call('e2e:auth-bootstrap');

        $output = Artisan::output();
        // Токен должен быть в выводе
        $this->assertNotEmpty(trim($output));
        // Проверяем, что это похоже на токен (длинная строка)
        $token = trim($output);
        $this->assertGreaterThan(20, strlen($token));
    }

    public function test_creates_token_for_user(): void
    {
        $user = User::firstOrCreate(
            ['email' => 'e2e@test.local'],
            [
                'name' => 'E2E Test User',
                'password' => Hash::make('test'),
                'role' => 'admin',
            ]
        );

        $initialTokenCount = $user->tokens()->count();

        Artisan::call('e2e:auth-bootstrap');

        $user->refresh();
        // Должен быть создан новый токен
        $this->assertGreaterThan($initialTokenCount, $user->tokens()->count());
    }

    public function test_accepts_custom_email(): void
    {
        $email = 'custom-e2e@test.local';
        User::where('email', $email)->delete();

        Artisan::call('e2e:auth-bootstrap', ['--email' => $email]);

        $this->assertDatabaseHas('users', ['email' => $email]);
    }

    public function test_accepts_custom_role(): void
    {
        $role = 'operator';
        Artisan::call('e2e:auth-bootstrap', ['--role' => $role]);

        $user = User::where('email', 'e2e@test.local')->first();
        $this->assertNotNull($user);
        $this->assertEquals($role, $user->role);
    }

    public function test_can_bootstrap_e2e_zone_fixture(): void
    {
        Zone::query()->where('uid', 'e2e-zone-main')->delete();
        Greenhouse::query()->where('uid', 'e2e-gh-main')->delete();

        Artisan::call('e2e:auth-bootstrap', [
            '--email' => 'agronomist@example.com',
            '--role' => 'admin',
            '--with-zone' => true,
        ]);

        $this->assertDatabaseHas('greenhouses', [
            'uid' => 'e2e-gh-main',
            'name' => 'E2E Greenhouse',
        ]);
        $this->assertDatabaseHas('zones', [
            'uid' => 'e2e-zone-main',
            'name' => 'E2E Zone',
            'status' => 'online',
        ]);
    }
}
