<?php

namespace App\Http\Middleware;

use Illuminate\Auth\Middleware\Authenticate as Middleware;
use Illuminate\Http\Request;

class Authenticate extends Middleware
{
    /**
     * Переопределяем редирект для API/JSON запросов, чтобы возвращать 401 вместо redirect.
     * Для Inertia запросов делаем редирект на страницу логина.
     */
    protected function redirectTo(Request $request): ?string
    {
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
}
