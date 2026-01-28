<?php

namespace App\Http\Middleware;

use Illuminate\Auth\Middleware\Authenticate as Middleware;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class Authenticate extends Middleware
{
    /**
     * Переопределяем редирект для API/JSON запросов, чтобы возвращать 401 вместо redirect.
     * Для Inertia запросов делаем редирект на страницу логина.
     */
    protected function redirectTo(Request $request): ?string
    {
        // Логируем попытку неаутентифицированного доступа
        $this->logUnauthenticatedAccess($request);

        // Для Inertia запросов делаем редирект (они имеют заголовок X-Inertia)
        if ($request->header('X-Inertia')) {
            return route('login');
        }

        // Для API и чистых JSON запросов возвращаем null (будет 401)
        if ($request->is('api/*') || ($request->expectsJson() && !$request->header('X-Inertia'))) {
            return null;
        }

        // Для обычных веб-запросов делаем редирект
        return route('login');
    }

    /**
     * Логирует попытку неаутентифицированного доступа
     */
    protected function logUnauthenticatedAccess(Request $request): void
    {
        $logContext = [
            'url' => $request->fullUrl(),
            'method' => $request->method(),
            'ip' => $request->ip(),
            'user_agent' => $request->userAgent(),
            'is_api' => $request->is('api/*'),
            'is_inertia' => $request->header('X-Inertia') !== null,
            'expects_json' => $request->expectsJson(),
            'has_auth_header' => $request->headers->has('Authorization'),
            'has_bearer_token' => $request->bearerToken() !== null,
            'has_session' => $request->hasSession(),
            'session_id' => $request->hasSession() ? $request->session()->getId() : null,
        ];

        // Проверяем наличие токена в заголовке
        $authHeader = $request->header('Authorization');
        if ($authHeader) {
            $logContext['auth_header_prefix'] = substr($authHeader, 0, 20);
        }

        // Проверяем наличие токена в server переменных (для nginx/FastCGI)
        $serverAuth = $request->server('HTTP_AUTHORIZATION') ?: $request->server('REDIRECT_HTTP_AUTHORIZATION');
        if ($serverAuth) {
            $logContext['server_auth_header_prefix'] = substr($serverAuth, 0, 20);
        }

        // Логируем как предупреждение (это нормальная ситуация для публичных endpoints)
        // Но важно отслеживать для безопасности
        Log::warning('Unauthenticated access attempt', $logContext);
    }
}
