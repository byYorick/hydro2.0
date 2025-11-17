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
        
        // Exclude API routes from CSRF verification
        $middleware->validateCsrfTokens(except: [
            'api/*',
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
    })->create();
