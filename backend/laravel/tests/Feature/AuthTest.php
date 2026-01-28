<?php

namespace Tests\Feature;

use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AuthTest extends TestCase
{
    use RefreshDatabase;

    public function test_login_me_logout_flow(): void
    {
        $user = User::factory()->create([
            'password' => 'password', // casts hashed
            'role' => 'viewer', // явно устанавливаем роль для теста
        ]);

        $resp = $this->postJson('/api/auth/login', [
            'email' => $user->email,
            'password' => 'password',
        ]);
        $resp->assertOk()->assertJsonStructure(['status', 'data' => ['token', 'user' => ['id', 'name', 'email', 'role', 'roles']]]);
        $token = $resp->json('data.token');
        
        // Проверяем, что роль возвращается
        $expectedRole = $user->role ?? 'viewer';
        $resp->assertJsonPath('data.user.role', $expectedRole);
        $resp->assertJsonPath('data.user.roles', [$expectedRole]);

        $me = $this->withHeader('Authorization', 'Bearer '.$token)->getJson('/api/auth/me');
        $me->assertOk()->assertJsonPath('data.user.email', $user->email);
        $me->assertJsonPath('data.user.role', $expectedRole);
        $me->assertJsonPath('data.user.roles', [$expectedRole]);

        $logout = $this->withHeader('Authorization', 'Bearer '.$token)->postJson('/api/auth/logout');
        $logout->assertOk();
    }
}


