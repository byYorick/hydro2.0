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
        // Trust all proxies (for Docker/nginx setup)
        $middleware->trustProxies(at: '*');
        $middleware->web(append: [
            \App\Http\Middleware\HandleInertiaRequests::class,
            \Illuminate\Http\Middleware\AddLinkHeadersForPreloadedAssets::class,
        ]);

        $middleware->alias([
            'admin' => \App\Http\Middleware\EnsureAdmin::class,
            'role' => \App\Http\Middleware\EnsureUserHasRole::class,
            'verify.python.service' => \App\Http\Middleware\VerifyPythonServiceToken::class,
            'auth.token' => \App\Http\Middleware\AuthenticateWithApiToken::class,
            'verify.alertmanager.webhook' => \App\Http\Middleware\VerifyAlertmanagerWebhook::class,
            'ip.whitelist' => \App\Http\Middleware\NodeRegistrationIpWhitelist::class,
        ]);
        
        // Rate limiting для регистрации нод будет настроен в AppServiceProvider

        // Rate Limiting для API роутов
        // Стандартный лимит: 120 запросов в минуту для всех API роутов
        // Более строгие лимиты применяются на уровне отдельных роутов
        // Увеличен для поддержки множественных компонентов на одной странице
        $middleware->api(prepend: [
            \Illuminate\Routing\Middleware\ThrottleRequests::class.':120,1',
        ]);

        // CSRF protection: исключаем только token-based API роуты и broadcasting
        // Session-based API роуты должны быть защищены CSRF
        $middleware->validateCsrfTokens(except: [
            'api/auth/*', // Token-based auth endpoints
            'api/python/*', // Python service token-based endpoints
            'api/nodes/register', // Node registration (token-based or public)
            'api/alerts/webhook', // Alertmanager webhook (protected by secret)
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
        // Генерируем корреляционный ID для отслеживания запросов
        $generateCorrelationId = function () {
            return 'req_'.uniqid().'_'.substr(md5(microtime(true)), 0, 8);
        };

        // Обрабатываем ThrottleRequestsException ПЕРВЫМ (до общего обработчика)
        // Используем HttpException вместо ThrottleRequestsException, так как ThrottleRequestsException наследуется от HttpException
        $exceptions->render(function (\Illuminate\Http\Exceptions\ThrottleRequestsException $e, \Illuminate\Http\Request $request) {
            $retryAfter = $e->getHeaders()['Retry-After'] ?? 60;
            
            if ($request->is('broadcasting/auth')) {
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
            
            // Для API роутов возвращаем JSON с 429
            if ($request->is('api/*') || $request->expectsJson()) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'RATE_LIMIT_EXCEEDED',
                    'message' => 'Too many requests. Please try again later.',
                ], 429)->withHeaders([
                    'Retry-After' => $retryAfter,
                ]);
            }
            
            // Для веб-роутов возвращаем стандартный ответ
            return response()->view('errors.429', [
                'retry_after' => $retryAfter,
            ], 429)->withHeaders([
                'Retry-After' => $retryAfter,
            ]);
        });

        // Централизованная обработка исключений для API и веб-маршрутов
        $exceptions->render(function (\Throwable $e, \Illuminate\Http\Request $request) use ($generateCorrelationId) {
            // Пропускаем обработку для broadcasting/auth (обрабатывается отдельно)
            if ($request->is('broadcasting/auth')) {
                return null;
            }

            $correlationId = $generateCorrelationId();
            $isDev = app()->environment(['local', 'testing', 'development']);
            $isApi = $request->is('api/*') || $request->expectsJson();
            $isInertia = $request->header('X-Inertia') !== null;

            // Логируем исключение с контекстом
            $logContext = [
                'correlation_id' => $correlationId,
                'url' => $request->fullUrl(),
                'method' => $request->method(),
                'ip' => $request->ip(),
                'user_agent' => $request->userAgent(),
                'user_id' => auth()->id(),
                'exception' => get_class($e),
                'message' => $e->getMessage(),
                'file' => $e->getFile(),
                'line' => $e->getLine(),
                'is_api' => $isApi,
                'is_inertia' => $isInertia,
            ];

            if ($isDev) {
                $logContext['trace'] = $e->getTraceAsString();
            }

            \Log::error('Exception', $logContext);

            // Обработка для API роутов
            if ($isApi) {

                $correlationId = $generateCorrelationId();
                $isDev = app()->environment(['local', 'testing', 'development']);

                // Логируем исключение с контекстом
                $logContext = [
                    'correlation_id' => $correlationId,
                    'url' => $request->fullUrl(),
                    'method' => $request->method(),
                    'ip' => $request->ip(),
                    'user_agent' => $request->userAgent(),
                    'user_id' => auth()->id(),
                    'exception' => get_class($e),
                    'message' => $e->getMessage(),
                    'file' => $e->getFile(),
                    'line' => $e->getLine(),
                ];

                if ($isDev) {
                    $logContext['trace'] = $e->getTraceAsString();
                }

                \Log::error('API Exception', $logContext);

                // Обработка специфичных исключений
                if ($e instanceof \Illuminate\Http\Exceptions\ThrottleRequestsException) {
                    $retryAfter = $e->getHeaders()['Retry-After'] ?? 60;
                    return response()->json([
                        'status' => 'error',
                        'code' => 'RATE_LIMIT_EXCEEDED',
                        'message' => 'Too many requests. Please try again later.',
                    ], 429)->withHeaders([
                        'Retry-After' => $retryAfter,
                    ]);
                }
                
                if ($e instanceof \Illuminate\Database\Eloquent\ModelNotFoundException) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'MODEL_NOT_FOUND',
                        'message' => 'Resource not found',
                        'correlation_id' => $correlationId,
                    ], 404);
                }

                if ($e instanceof \Illuminate\Auth\AuthenticationException) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'UNAUTHENTICATED',
                        'message' => 'Unauthenticated',
                        'correlation_id' => $correlationId,
                    ], 401);
                }

                if ($e instanceof \Illuminate\Auth\Access\AuthorizationException) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'UNAUTHORIZED',
                        'message' => 'This action is unauthorized',
                        'correlation_id' => $correlationId,
                    ], 403);
                }

                if ($e instanceof \Illuminate\Validation\ValidationException) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'VALIDATION_ERROR',
                        'message' => 'Validation failed',
                        'errors' => $e->errors(),
                        'correlation_id' => $correlationId,
                    ], 422);
                }

                if ($e instanceof \Illuminate\Http\Client\RequestException ||
                    $e instanceof \Illuminate\Http\Client\ConnectionException ||
                    $e instanceof \Illuminate\Http\Client\TimeoutException) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'SERVICE_UNAVAILABLE',
                        'message' => 'External service unavailable',
                        'correlation_id' => $correlationId,
                    ], 503);
                }

                // Общая обработка для всех остальных исключений
                $response = [
                    'status' => 'error',
                    'code' => 'INTERNAL_ERROR',
                    'message' => $isDev ? $e->getMessage() : 'Internal server error',
                    'correlation_id' => $correlationId,
                ];

                if ($isDev) {
                    $response['exception'] = get_class($e);
                    $response['file'] = $e->getFile();
                    $response['line'] = $e->getLine();
                    $response['trace'] = $e->getTraceAsString();
                }

                return response()->json($response, 500);
            }

            // Обработка для веб/Inertia маршрутов
            if ($isInertia || $request->is('*')) {
                // Для Inertia запросов возвращаем Inertia-ответ с ошибкой
                if ($isInertia) {
                    return \Inertia\Inertia::render('Error', [
                        'status' => 500,
                        'message' => $isDev ? $e->getMessage() : 'Произошла ошибка. Пожалуйста, попробуйте позже.',
                        'correlation_id' => $correlationId,
                        'exception' => $isDev ? get_class($e) : null,
                        'file' => $isDev ? $e->getFile() : null,
                        'line' => $isDev ? $e->getLine() : null,
                    ])->toResponse($request)->setStatusCode(500);
                }

                // Для обычных веб-запросов возвращаем дружелюбную страницу ошибки
                if ($e instanceof \Illuminate\Database\Eloquent\ModelNotFoundException) {
                    return response()->view('errors.404', [
                        'correlation_id' => $correlationId,
                    ], 404);
                }

                if ($e instanceof \Illuminate\Auth\AuthenticationException) {
                    return redirect()->route('login')->with('error', 'Требуется авторизация.');
                }

                if ($e instanceof \Illuminate\Auth\Access\AuthorizationException) {
                    return response()->view('errors.403', [
                        'correlation_id' => $correlationId,
                        'message' => 'Доступ запрещен.',
                    ], 403);
                }

                if ($e instanceof \Illuminate\Validation\ValidationException) {
                    return back()->withErrors($e->errors())->withInput();
                }

                // Общая ошибка для веб-маршрутов
                return response()->view('errors.500', [
                    'correlation_id' => $correlationId,
                    'message' => $isDev ? $e->getMessage() : 'Произошла ошибка. Пожалуйста, попробуйте позже.',
                    'exception' => $isDev ? get_class($e) : null,
                    'file' => $isDev ? $e->getFile() : null,
                    'line' => $isDev ? $e->getLine() : null,
                ], 500);
            }

            return null;
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
