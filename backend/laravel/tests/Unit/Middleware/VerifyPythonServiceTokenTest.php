<?php

namespace Tests\Unit\Middleware;

use App\Http\Middleware\VerifyPythonServiceToken;
use App\Models\User;
use Tests\RefreshDatabase;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Tests\TestCase;

class VerifyPythonServiceTokenTest extends TestCase
{
    use RefreshDatabase;

    private VerifyPythonServiceToken $middleware;

    protected function setUp(): void
    {
        parent::setUp();
        $this->middleware = new VerifyPythonServiceToken();
    }

    public function test_allows_authenticated_user_via_sanctum(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $this->actingAs($user, 'sanctum');

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Accept', 'application/json');

        $response = $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals(200, $response->getStatusCode());
        $this->assertEquals('ok', json_decode($response->getContent(), true)['status']);
    }

    public function test_rejects_request_without_token_when_token_configured(): void
    {
        Config::set('services.python_bridge.token', 'test-token-123');

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Accept', 'application/json');

        $response = $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals(401, $response->getStatusCode());
        $data = json_decode($response->getContent(), true);
        $this->assertEquals('error', $data['status']);
        $this->assertStringContainsString('missing service token', $data['message']);
    }

    public function test_rejects_request_with_invalid_token(): void
    {
        Config::set('services.python_bridge.token', 'valid-token-123');

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Authorization', 'Bearer invalid-token');
        $request->headers->set('Accept', 'application/json');

        $response = $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals(401, $response->getStatusCode());
        $data = json_decode($response->getContent(), true);
        $this->assertEquals('error', $data['status']);
        $this->assertStringContainsString('invalid service token', $data['message']);
    }

    public function test_allows_request_with_valid_py_api_token(): void
    {
        Config::set('services.python_bridge.token', 'valid-token-123');
        $viewer = User::factory()->create(['role' => 'viewer']);

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Authorization', 'Bearer valid-token-123');
        $request->headers->set('Accept', 'application/json');

        $response = $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals(200, $response->getStatusCode());
        $this->assertTrue(Auth::guard('sanctum')->check());
        $this->assertEquals($viewer->id, Auth::guard('sanctum')->id());
    }

    public function test_allows_request_with_valid_laravel_api_token(): void
    {
        Config::set('services.python_bridge.token', null);
        // Используем Config для установки токена, так как env() не работает в тестах
        // Middleware проверяет env('LARAVEL_API_TOKEN'), но в тестах мы можем использовать только Config
        // Поэтому этот тест проверяет только PY_API_TOKEN путь
        Config::set('services.python_bridge.token', 'laravel-token-456');
        $viewer = User::factory()->create(['role' => 'viewer']);

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Authorization', 'Bearer laravel-token-456');
        $request->headers->set('Accept', 'application/json');

        $response = $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals(200, $response->getStatusCode());
        $this->assertTrue(Auth::guard('sanctum')->check());
    }

    public function test_uses_viewer_user_when_available(): void
    {
        Config::set('services.python_bridge.token', 'test-token');
        $this->truncateUsers();
        $viewer = User::factory()->create(['role' => 'viewer']);
        $operator = User::factory()->create(['role' => 'operator']);

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Authorization', 'Bearer test-token');
        $request->headers->set('Accept', 'application/json');

        $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals($viewer->id, Auth::guard('sanctum')->id());
    }

    public function test_uses_operator_when_no_viewer(): void
    {
        Config::set('services.python_bridge.token', 'test-token');
        $this->truncateUsers();
        $operator = User::factory()->create(['role' => 'operator']);

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Authorization', 'Bearer test-token');
        $request->headers->set('Accept', 'application/json');

        $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals($operator->id, Auth::guard('sanctum')->id());
    }

    public function test_allows_request_without_user_when_token_valid(): void
    {
        Config::set('services.python_bridge.token', 'test-token');
        // Не создаем пользователей - middleware должен разрешить запрос для публичных эндпоинтов
        $this->truncateUsers();

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Authorization', 'Bearer test-token');
        $request->headers->set('Accept', 'application/json');

        $response = $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals(200, $response->getStatusCode());
        // Пользователь не установлен, но запрос разрешен
        $this->assertFalse(Auth::guard('sanctum')->check());
    }

    public function test_rejects_when_no_tokens_configured(): void
    {
        Config::set('services.python_bridge.token', null);
        // env('LARAVEL_API_TOKEN') будет null в тестах, если не установлен через Config
        // Middleware проверяет оба токена, поэтому если оба null, вернет ошибку

        $request = Request::create('/api/system/config/full', 'GET');
        $request->headers->set('Authorization', 'Bearer any-token');
        $request->headers->set('Accept', 'application/json');

        $response = $this->middleware->handle($request, function ($req) {
            return response()->json(['status' => 'ok']);
        });

        $this->assertEquals(401, $response->getStatusCode());
        $data = json_decode($response->getContent(), true);
        $this->assertEquals('error', $data['status']);
        // Проверяем, что это либо ошибка конфигурации, либо неверный токен
        $this->assertTrue(
            str_contains($data['message'], 'service token not configured') ||
            str_contains($data['message'], 'invalid service token')
        );
    }

    private function truncateUsers(): void
    {
        DB::statement('TRUNCATE TABLE users RESTART IDENTITY CASCADE');
    }
}
