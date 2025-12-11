<?php

namespace App\Http\Middleware;

use App\Models\User;
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
     * При успешной валидации сервисного токена устанавливает сервисного пользователя.
     */
    public function handle(Request $request, Closure $next): Response
    {
        // Сначала проверяем, авторизован ли пользователь через Sanctum
        if (Auth::guard('sanctum')->check()) {
            Log::debug('Python service route accessed by authenticated user via Sanctum');

            return $next($request);
        }

        // Если пользователь не авторизован, проверяем токен Python сервисов
        // Поддерживаем два типа токенов:
        // 1. PY_API_TOKEN (services.python_bridge.token) - основной токен для Python сервисов
        // 2. LARAVEL_API_TOKEN - токен для сервисов, обращающихся к Laravel API
        $pyApiToken = Config::get('services.python_bridge.token');
        $laravelApiToken = env('LARAVEL_API_TOKEN');

        // Если ни один токен не настроен, всегда запрещаем доступ
        if (! $pyApiToken && ! $laravelApiToken) {
            Log::error('Python service token not configured: neither PY_API_TOKEN nor LARAVEL_API_TOKEN is set', [
                'url' => $request->fullUrl(),
                'ip' => $request->ip(),
                'env' => config('app.env'),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: service token not configured or missing authentication',
            ], 401);
        }

        $providedToken = $request->bearerToken();

        if (! $providedToken) {
            Log::warning('Python service request missing Authorization header', [
                'url' => $request->fullUrl(),
                'ip' => $request->ip(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: missing service token',
            ], 401);
        }

        // Проверяем оба токена
        $tokenValid = false;
        if ($pyApiToken && hash_equals($pyApiToken, $providedToken)) {
            $tokenValid = true;
        } elseif ($laravelApiToken && hash_equals($laravelApiToken, $providedToken)) {
            $tokenValid = true;
        }

        if (! $tokenValid) {
            // НЕ логируем части токена - это утечка секрета
            // Логируем только факт ошибки и контекст запроса
            Log::warning('Python service request with invalid token', [
                'url' => $request->fullUrl(),
                'ip' => $request->ip(),
                'user_agent' => $request->userAgent(),
                'method' => $request->method(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: invalid service token',
            ], 401);
        }

        // Токен валиден - устанавливаем сервисного пользователя, если он существует
        // Для публичных эндпоинтов (например, /api/system/config/full) пользователь не обязателен
        $serviceUser = $this->getServiceUser();
        if ($serviceUser) {
            Auth::guard('sanctum')->setUser($serviceUser);
            Auth::guard('web')->setUser($serviceUser);
            $request->setUserResolver(static fn () => $serviceUser);
            Log::debug('Python service token verified successfully, service user set', [
                'user_id' => $serviceUser->id,
            ]);
        } else {
            // Пользователь не найден, но токен валиден - разрешаем запрос для публичных эндпоинтов
            // Логируем только один раз, чтобы не засорять логи
            static $logged = false;
            if (!$logged) {
                Log::info('Python service token verified but service user not found - allowing request for public endpoints', [
                    'note' => 'Consider creating a viewer user for better security and authorization',
                ]);
                $logged = true;
            }
        }

        return $next($request);
    }

    /**
     * Получить или создать сервисного пользователя для Python сервисов.
     *
     * ВАЖНО: Сервисный токен дает доступ только к /api/system/config/full (чтение конфигурации).
     * Для безопасности используем пользователя с минимальными правами (viewer), а не админа.
     * Это ограничивает потенциальный ущерб при компрометации токена.
     */
    private function getServiceUser(): ?User
    {
        // Пытаемся найти пользователя с ролью viewer (минимальные права - только чтение)
        $viewer = User::where('role', 'viewer')->first();
        if ($viewer) {
            return $viewer;
        }

        // Если viewer нет, используем оператора (но не админа для безопасности)
        $operator = User::whereIn('role', ['operator', 'engineer', 'agronomist'])->first();
        if ($operator) {
            return $operator;
        }

        // В крайнем случае используем админа, но логируем предупреждение
        $admin = User::where('role', 'admin')->first();
        if ($admin) {
            Log::warning('Service token using admin user - consider creating a viewer user for better security', [
                'admin_id' => $admin->id,
            ]);

            return $admin;
        }

        // Если нет подходящих пользователей, возвращаем первого пользователя
        // (в продакшене должен быть хотя бы один пользователь)
        $user = User::first();
        if ($user) {
            Log::warning('Service token using first available user - consider creating a dedicated viewer user', [
                'user_id' => $user->id,
                'role' => $user->role ?? 'unknown',
            ]);
        }

        return $user;
    }
}
