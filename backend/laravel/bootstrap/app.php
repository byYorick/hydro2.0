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
            '_boost/browser-logs',
        ]);

        // Note: Session middleware is NOT added globally to API routes
        // because API routes use mixed authentication:
        // - Token-based (Sanctum) for /api/auth/* endpoints
        // - Session-based (auth middleware) for Inertia.js routes
        // Session middleware should be added conditionally per route group if needed
        // If session middleware is needed, EncryptCookies must come before StartSession
    })
    ->withExceptions(function (Exceptions $exceptions) {
        // Обрабатываем ThrottleRequestsException для broadcasting/auth (возвращаем 429 вместо 500)
        $exceptions->render(function (\Illuminate\Routing\Middleware\ThrottleRequestsException $e, \Illuminate\Http\Request $request) {
            if ($request->is('broadcasting/auth')) {
                $retryAfter = $e->getHeaders()['Retry-After'] ?? 60;
                \Log::warning('Broadcasting auth: Rate limit exceeded', [
                    'ip' => $request->ip(),
                    'channel' => $request->input('channel_name'),
                    'retry_after' => $retryAfter,
                ]);
                return response()->json([
                    'message' => 'Too Many Attempts.',
                ], 429)->withHeaders([
                    'Retry-After' => $retryAfter,
                ]);
            }
        });
        
        // Обрабатываем исключения для broadcasting/auth
        $exceptions->render(function (\Illuminate\Auth\AuthenticationException $e, \Illuminate\Http\Request $request) {
            if ($request->is('broadcasting/auth')) {
                \Log::warning('Broadcasting auth: Authentication exception in middleware', [
                    'ip' => $request->ip(),
                    'user_agent' => $request->userAgent(),
                    'channel' => $request->input('channel_name'),
                    'error' => $e->getMessage(),
                ]);
                return response()->json(['message' => 'Unauthenticated.'], 403);
            }
        });
        
        // Обрабатываем все остальные исключения для broadcasting/auth
        $exceptions->render(function (\Exception $e, \Illuminate\Http\Request $request) {
            if ($request->is('broadcasting/auth')) {
                $isDev = app()->environment(['local', 'testing', 'development']);
                
                if ($isDev) {
                    \Log::error('Broadcasting auth: Exception in middleware or route', [
                        'ip' => $request->ip(),
                        'error' => $e->getMessage(),
                        'trace' => $e->getTraceAsString(),
                    ]);
                } else {
                    \Log::error('Broadcasting auth: Exception in middleware or route', [
                        'ip' => $request->ip(),
                        'error' => $e->getMessage(),
                    ]);
                }
                
                // Возвращаем 403 вместо 500 для ошибок авторизации
                if ($e instanceof \Illuminate\Auth\AuthenticationException) {
                    return response()->json(['message' => 'Unauthenticated.'], 403);
                }
                
                // Для остальных ошибок возвращаем 500, но с безопасным сообщением
                return response()->json(['message' => 'Authorization failed.'], 500);
            }
        });
    })
    ->withEvents(discover: [
        'App\Listeners',
    ])
    ->create();
