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
        // Проверяем сервисный токен ДО Sanctum.
        // Иначе каждый service-to-service запрос с Bearer token сначала ударяет в
        // personal_access_tokens, что делает внутренние API зависимыми от БД даже
        // когда достаточно статического service token.
        $pyApiToken = Config::get('services.python_bridge.token');
        $laravelApiToken = env('LARAVEL_API_TOKEN');
        $providedToken = $request->bearerToken();

        if ($providedToken) {
            $tokenValid = false;
            if ($pyApiToken && hash_equals($pyApiToken, $providedToken)) {
                $tokenValid = true;
            } elseif ($laravelApiToken && hash_equals($laravelApiToken, $providedToken)) {
                $tokenValid = true;
            }

            if ($tokenValid) {
                $request->attributes->set('python_service_authenticated', true);

                $serviceUser = $this->getServiceUser();
                if ($serviceUser) {
                    Auth::guard('sanctum')->setUser($serviceUser);
                    Auth::guard('web')->setUser($serviceUser);
                    $request->setUserResolver(static fn () => $serviceUser);
                } else {
                    static $logged = false;
                    if (! $logged) {
                        Log::info('Python service token verified but service user not found - allowing request for public endpoints', [
                            'note' => 'Consider creating a viewer user for better security and authorization',
                        ]);
                        $logged = true;
                    }
                }

                return $next($request);
            }
        }

        // Если сервисный токен не подошёл, разрешаем доступ авторизованным пользователям через Sanctum.
        if (Auth::guard('sanctum')->check()) {
            return $next($request);
        }

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
        $viewer = User::where('role', 'viewer')->latest('id')->first();
        if ($viewer) {
            return $viewer;
        }

        // Если viewer нет, используем оператора (но не админа для безопасности)
        $operator = User::whereIn('role', ['operator', 'engineer', 'agronomist'])->latest('id')->first();
        if ($operator) {
            return $operator;
        }

        // В крайнем случае используем админа, но логируем предупреждение
        $admin = User::where('role', 'admin')->latest('id')->first();
        if ($admin) {
            Log::warning('Service token using admin user - consider creating a viewer user for better security', [
                'admin_id' => $admin->id,
            ]);

            return $admin;
        }

        // Если нет подходящих пользователей, возвращаем первого пользователя
        // (в продакшене должен быть хотя бы один пользователь)
        $user = User::latest('id')->first();
        if ($user) {
            Log::warning('Service token using first available user - consider creating a dedicated viewer user', [
                'user_id' => $user->id,
                'role' => $user->role ?? 'unknown',
            ]);
        }

        return $user;
    }
}
