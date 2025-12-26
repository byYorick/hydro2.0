<?php

/*
|--------------------------------------------------------------------------
| Base Web Routes
|--------------------------------------------------------------------------
|
| Основные веб-маршруты для аутентификации, broadcasting и базовых страниц.
| Не содержит маршруты для greenhouses/zones/nodes - они в отдельных файлах.
|
*/

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\PlantController;
use App\Http\Controllers\ProfileController;
use App\Models\Alert;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Recipe;
use App\Models\SystemLog;
use App\Models\TelemetryLast;
use App\Models\Zone;
// ZoneCycle removed in refactor - using GrowCycle instead
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Broadcast;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Route;
use Inertia\Inertia;

// Роут для Laravel Boost browser-logs
// В проде отключен для предотвращения DoS и утечки данных
// В dev режиме доступен только для авторизованных пользователей с throttle
Route::match(['GET', 'POST'], '/_boost/browser-logs', function (\Illuminate\Http\Request $request) {
    // В проде полностью отключаем эндпоинт
    if (app()->environment('production')) {
        \Log::warning('Browser log endpoint accessed in production (blocked)', [
            'ip' => $request->ip(),
            'user_agent' => $request->userAgent(),
            'method' => $request->method(),
        ]);

        return response()->json(['status' => 'disabled'], 404);
    }

    // Для GET запросов просто возвращаем 200 (может использоваться для проверки доступности)
    if ($request->isMethod('GET')) {
        return response()->json(['status' => 'ok', 'method' => 'GET'], 200);
    }

    // В dev режиме требуем аутентификацию и валидацию для POST запросов
    if (! auth()->check()) {
        \Log::warning('Browser log endpoint: unauthenticated request', [
            'ip' => $request->ip(),
            'user_agent' => $request->userAgent(),
            'method' => $request->method(),
        ]);

        return response()->json(['status' => 'unauthorized'], 403);
    }

    // Валидируем и ограничиваем размер данных
    $validated = $request->validate([
        'level' => ['nullable', 'string', 'in:log,info,warn,error'],
        'message' => ['nullable', 'string', 'max:1000'],
        'data' => ['nullable', 'array', 'max:10'], // Ограничиваем количество полей
    ]);

    // Логируем только валидированные данные
    \Log::debug('Browser log received (dev only)', [
        'user_id' => auth()->id(),
        'level' => $validated['level'] ?? 'log',
        'message' => $validated['message'] ?? null,
        'data_keys' => isset($validated['data']) ? array_keys($validated['data']) : [],
    ]);

    return response()->json(['status' => 'ok'], 200);
})->middleware(['web', 'auth', 'throttle:120,1']); // 120 запросов в минуту для dev режима

// Broadcasting authentication route
// Rate limiting: 300 запросов в минуту для поддержки множественных каналов и переподключений
// Поддерживает как сессионную авторизацию (web guard), так и токеновую (Sanctum PAT)
Route::post('/broadcasting/auth', function (\Illuminate\Http\Request $request) {
    try {
        // Сначала пытаемся аутентифицировать через Sanctum PAT (для мобильных/SPA клиентов)
        // Это позволяет использовать токен из /api/auth/login для WebSocket авторизации
        $user = null;

        // Проверяем Sanctum токен из заголовка Authorization
        if ($request->bearerToken()) {
            $token = \Laravel\Sanctum\PersonalAccessToken::findToken($request->bearerToken());
            if ($token && $token->tokenable) {
                // Проверяем срок действия токена
                if ($token->expires_at && $token->expires_at->isPast()) {
                    \Log::warning('Broadcasting auth: Sanctum token expired', [
                        'ip' => $request->ip(),
                        'token_id' => $token->id,
                    ]);

                    return response()->json(['message' => 'Token expired.'], 403);
                }

                $user = $token->tokenable;
                // Устанавливаем пользователя для обоих guard'ов
                \Illuminate\Support\Facades\Auth::guard('sanctum')->setUser($user);
                \Illuminate\Support\Facades\Auth::guard('web')->setUser($user);
                $request->setUserResolver(static fn () => $user);

                // Обновляем last_used_at для отслеживания активности токена
                $token->forceFill(['last_used_at' => now()])->save();

                \Log::debug('Broadcasting auth: Authenticated via Sanctum PAT', [
                    'user_id' => $user->id,
                    'channel' => $request->input('channel_name'),
                ]);
            }
        }

        // Если не удалось аутентифицировать через токен, проверяем сессию (web guard)
        if (! $user) {
            if (! auth()->check() && ! auth('web')->check()) {
                \Log::warning('Broadcasting auth: Unauthenticated request', [
                    'ip' => $request->ip(),
                    'user_agent' => $request->userAgent(),
                    'channel' => $request->input('channel_name'),
                    'has_bearer_token' => $request->bearerToken() !== null,
                ]);

                return response()->json(['message' => 'Unauthenticated.'], 403);
            }
            $user = auth()->user() ?? auth('web')->user();
        }

        \Log::debug('Broadcasting auth: Starting authorization', [
            'channel' => $request->input('channel_name'),
            'user_authenticated' => $user !== null,
            'auth_method' => $request->bearerToken() ? 'sanctum_token' : 'session',
        ]);

        if (! $user) {
            \Log::error('Broadcasting auth: User is null after authentication attempts', [
                'ip' => $request->ip(),
                'channel' => $request->input('channel_name'),
            ]);

            return response()->json(['message' => 'Unauthenticated.'], 403);
        }

        $channelName = $request->input('channel_name');

        \Log::debug('Broadcasting auth: Authorizing channel', [
            'user_id' => $user->id,
            'channel' => $channelName,
        ]);

        // Обрабатываем ошибки БД отдельно
        try {
            $response = Broadcast::auth($request);

            // Проверяем, что ответ валиден
            if (! $response) {
                \Log::warning('Broadcasting auth: Broadcast::auth returned null', [
                    'user_id' => $user->id,
                    'channel' => $channelName,
                ]);

                return response()->json(['message' => 'Authorization failed.'], 403);
            }

            return $response;
        } catch (\Illuminate\Database\QueryException $dbException) {
            $isDev = app()->environment(['local', 'testing', 'development']);
            $errorMessage = $dbException->getMessage();
            $isMissingTable = str_contains($errorMessage, 'no such table') ||
                             str_contains($errorMessage, "doesn't exist") ||
                             str_contains($errorMessage, 'relation does not exist');

            if ($isDev) {
                \Log::error('Broadcasting auth: Database error', [
                    'user_id' => $user->id,
                    'channel' => $channelName,
                    'error' => $errorMessage,
                    'sql_state' => $dbException->getCode(),
                    'is_missing_table' => $isMissingTable,
                ]);
            } else {
                \Log::error('Broadcasting auth: Database error', [
                    'user_id' => $user->id,
                    'channel' => $channelName,
                    'error_type' => $isMissingTable ? 'missing_table' : 'connection_error',
                ]);
            }

            if ($isDev) {
                if ($isMissingTable) {
                    return response()->json([
                        'message' => 'Database schema not initialized. Please run migrations.',
                        'error' => 'Missing database table',
                        'hint' => 'Run: php artisan migrate',
                    ], 503);
                }

                return response()->json([
                    'message' => 'Service temporarily unavailable. Please check database connection.',
                    'error' => 'Database connection error',
                ], 503);
            } else {
                return response()->json([
                    'message' => 'Service temporarily unavailable.',
                ], 503);
            }
        } catch (\PDOException $pdoException) {
            $isDev = app()->environment(['local', 'testing', 'development']);

            if ($isDev) {
                \Log::error('Broadcasting auth: PDO error', [
                    'user_id' => $user->id ?? null,
                    'channel' => $channelName ?? null,
                    'error' => $pdoException->getMessage(),
                    'code' => $pdoException->getCode(),
                ]);
            } else {
                \Log::error('Broadcasting auth: PDO error', [
                    'user_id' => $user->id ?? null,
                    'channel' => $channelName ?? null,
                    'error_type' => 'pdo_connection_error',
                ]);
            }

            if ($isDev) {
                return response()->json([
                    'message' => 'Database connection error. Please check database configuration.',
                    'error' => 'PDO error',
                ], 503);
            } else {
                return response()->json([
                    'message' => 'Service temporarily unavailable.',
                ], 503);
            }
        }

        \Log::debug('Broadcasting auth: Success', [
            'user_id' => $user->id,
            'channel' => $channelName,
            'status' => $response->getStatusCode(),
        ]);

        return $response;
    } catch (\Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException $e) {
        // PusherBroadcaster::auth throws AccessDeniedHttpException for unauthorized / invalid channel_name/socket_id.
        // Treat it as 403 to avoid turning auth failures into 500s (important for E2E clarity).
        \Log::warning('Broadcasting auth: Access denied', [
            'ip' => $request->ip(),
            'channel' => $request->input('channel_name'),
            'user_id' => auth()->id(),
        ]);

        return response()->json(['message' => 'Unauthorized.'], 403);
    } catch (\Illuminate\Broadcasting\BroadcastException $broadcastException) {
        // Отказ в доступе к каналу - возвращаем 403, а не 500
        \Log::warning('Broadcasting auth: Channel authorization denied', [
            'user_id' => auth()->id(),
            'channel' => $request->input('channel_name'),
            'error' => $broadcastException->getMessage(),
        ]);

        return response()->json(['message' => 'Unauthorized.'], 403);
    } catch (\Exception $e) {
        $isDev = app()->environment(['local', 'testing', 'development']);

        if ($isDev) {
            \Log::error('Broadcasting auth: Error', [
                'user_id' => auth()->id(),
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);
        } else {
            \Log::error('Broadcasting auth: Error', [
                'user_id' => auth()->id(),
                'error' => $e->getMessage(),
            ]);
        }

        return response()->json(['message' => 'Authorization failed.'], 500);
    }
})
    // IMPORTANT: allow token-based auth for WS clients (E2E runner, mobile, etc.).
    // The handler itself supports both session and Sanctum PAT; do not block it with the default auth middleware.
    ->withoutMiddleware([\Illuminate\Auth\Middleware\Authenticate::class, \App\Http\Middleware\HandleInertiaRequests::class])
    ->middleware(['web', \App\Http\Middleware\AuthenticateWithApiToken::class, 'throttle:300,1']); // Rate limiting: 300/min
