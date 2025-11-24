<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class VerifyPythonServiceToken
{
    /**
     * Handle an incoming request.
     *
     * Проверяет токен Python сервисов из заголовка Authorization.
     * Токен должен совпадать с PY_API_TOKEN из конфигурации.
     * Также разрешает доступ авторизованным пользователям через Sanctum.
     */
    public function handle(Request $request, Closure $next): Response
    {
        // Сначала проверяем, авторизован ли пользователь через Sanctum
        if (Auth::guard('sanctum')->check()) {
            Log::debug('Python service route accessed by authenticated user via Sanctum');
            return $next($request);
        }
        
        // Если пользователь не авторизован, проверяем токен Python сервисов
        $expectedToken = Config::get('services.python_bridge.token');
        
        // Если токен не настроен
        if (!$expectedToken) {
            // В dev режиме разрешаем доступ без токена (только для локальной разработки)
            if (config('app.env') === 'local' || config('app.debug')) {
                Log::info('Python service token not configured, allowing access in dev mode', [
                    'url' => $request->fullUrl(),
                    'ip' => $request->ip(),
                ]);
                return $next($request);
            }
            
            // В production режиме требуем токен
            Log::warning('Python service token not configured in services.python_bridge.token', [
                'url' => $request->fullUrl(),
                'ip' => $request->ip(),
            ]);
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: service token not configured or missing authentication',
            ], 401);
        }
        
        $providedToken = $request->bearerToken();
        
        if (!$providedToken) {
            Log::warning('Python service request missing Authorization header', [
                'url' => $request->fullUrl(),
                'ip' => $request->ip(),
            ]);
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: missing service token',
            ], 401);
        }
        
        if (!hash_equals($expectedToken, $providedToken)) {
            Log::warning('Python service request with invalid token', [
                'url' => $request->fullUrl(),
                'ip' => $request->ip(),
                'expected_length' => strlen($expectedToken),
                'provided_length' => strlen($providedToken),
                'expected_prefix' => substr($expectedToken, 0, 10),
                'provided_prefix' => substr($providedToken, 0, 10),
            ]);
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: invalid service token',
            ], 401);
        }
        
        Log::debug('Python service token verified successfully');
        return $next($request);
    }
}

