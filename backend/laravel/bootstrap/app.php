<?php

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware) {
        $middleware->web(append: [
            \App\Http\Middleware\HandleInertiaRequests::class,
            \Illuminate\Http\Middleware\AddLinkHeadersForPreloadedAssets::class,
        ]);

        $middleware->alias([
            'admin' => \App\Http\Middleware\EnsureAdmin::class,
            'role' => \App\Http\Middleware\EnsureUserHasRole::class,
            'verify.python.service' => \App\Http\Middleware\VerifyPythonServiceToken::class,
            'auth.token' => \App\Http\Middleware\AuthenticateWithApiToken::class,
        ]);

        // Rate Limiting для API роутов
        // Стандартный лимит: 60 запросов в минуту для всех API роутов
        // Более строгие лимиты применяются на уровне отдельных роутов
        $middleware->api(prepend: [
            \Illuminate\Routing\Middleware\ThrottleRequests::class.':60,1',
        ]);

        // Exclude API routes and broadcasting auth from CSRF verification
        $middleware->validateCsrfTokens(except: [
            'api/*',
            'broadcasting/auth',
            '_boost/browser-logs', // ИСПРАВЛЕНО: Исключаем browser-logs из CSRF проверки
        ]);

        // Note: Session middleware is NOT added globally to API routes
        // because API routes use mixed authentication:
        // - Token-based (Sanctum) for /api/auth/* endpoints
        // - Session-based (auth middleware) for Inertia.js routes
        // Session middleware should be added conditionally per route group if needed
        // If session middleware is needed, EncryptCookies must come before StartSession
    })
    ->withExceptions(function (Exceptions $exceptions) {
        //
    })
    ->withEvents(discover: [
        'App\Listeners',
    ])
    ->create();
