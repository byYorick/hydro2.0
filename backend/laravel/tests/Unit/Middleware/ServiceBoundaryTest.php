<?php

namespace Tests\Unit\Middleware;

use App\Http\Middleware\VerifyPythonServiceToken;
use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Config;
use Tests\TestCase;

class ServiceBoundaryTest extends TestCase
{
    public function test_user_roles_cannot_cross_service_boundary(): void
    {
        Config::set('services.python_bridge.token', 'test-service-secret');
        Config::set('services.python_bridge.laravel_api_token', null);
        foreach (['viewer', 'operator', 'admin'] as $role) {
            $user = new User;
            $user->id = 42;
            $user->role = $role;
            $this->actingAs($user, 'sanctum');
            foreach (['/api/internal/grow-cycles/42/harvest', '/api/internal/realtime/telemetry-batch', '/api/node-channels/42'] as $path) {
                $request = Request::create($path, 'POST');
                $response = (new VerifyPythonServiceToken)->handle($request, fn () => response('unexpected', 200));
                $this->assertSame(401, $response->getStatusCode(), "$role: $path");
            }
        }
    }

    public function test_explicit_mixed_boundary_preserves_sanctum_access(): void
    {
        Config::set('services.python_bridge.token', 'test-service-secret');
        $user = new User;
        $user->id = 42;
        $this->actingAs($user, 'sanctum');
        $response = (new VerifyPythonServiceToken)->handle(Request::create('/api/system/config/full'), fn () => response('ok'), 'true');
        $this->assertSame(200, $response->getStatusCode());
    }
}
