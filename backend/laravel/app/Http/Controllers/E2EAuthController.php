<?php

namespace App\Http\Controllers;

use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;

class E2EAuthController extends Controller
{
    /**
     * Создать пользователя и токен для E2E тестов.
     * Доступно только в testing/e2e окружении.
     */
    public function createToken(Request $request): JsonResponse
    {
        // Проверяем, что мы в тестовом окружении
        $env = app()->environment();
        if (! in_array($env, ['testing', 'e2e'], true)) {
            abort(404, 'Not found');
        }

        $validated = $request->validate([
            'email' => ['nullable', 'email', 'max:255'],
            'role' => ['nullable', 'string', 'in:admin,operator,viewer,agronomist,engineer'],
        ]);

        $email = $validated['email'] ?? 'e2e@test.local';
        $role = $validated['role'] ?? 'admin';

        // Создаем или получаем пользователя
        $user = User::firstOrCreate(
            ['email' => $email],
            [
                'name' => 'E2E Test User',
                'password' => Hash::make('e2e-test-password'),
                'role' => $role,
                'email_verified_at' => now(),
            ]
        );

        // Обновляем роль, если пользователь уже существовал
        if ($user->role !== $role) {
            $user->role = $role;
            $user->save();
        }

        // Создаем новый токен
        $token = $user->createToken('e2e-test-token')->plainTextToken;

        return response()->json([
            'status' => 'ok',
            'data' => [
                'token' => $token,
                'user' => [
                    'id' => $user->id,
                    'email' => $user->email,
                    'role' => $user->role,
                ],
            ],
        ]);
    }
}
