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
        ]);
        
        // Exclude API routes from CSRF verification for session-based auth
        $middleware->validateCsrfTokens(except: [
            'api/*',
        ]);
        
        // Add session middleware to API routes for session-based authentication
        $middleware->api(prepend: [
            \Illuminate\Session\Middleware\StartSession::class,
            \Illuminate\Cookie\Middleware\EncryptCookies::class,
        ]);
    })
    ->withExceptions(function (Exceptions $exceptions) {
        //
    })->create();
