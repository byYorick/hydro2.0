<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Laravel\Sanctum\PersonalAccessToken;

class AuthenticateWithApiToken
{
    /**
     * Attempt to authenticate the incoming request using a Sanctum personal access token.
     * Falls back to the default session guard so the existing 'auth' middleware can pass.
     */
    public function handle(Request $request, Closure $next)
    {
        if (config('app.env') === 'testing' && str_starts_with($request->path(), 'api/zones')) {
            $hdr = $request->header('Authorization');
            $bearer = $request->bearerToken();
            Log::warning('AuthenticateWithApiToken(debug): incoming api/zones request', [
                'has_authorization_header' => $request->headers->has('Authorization'),
                'authorization_header_prefix' => is_string($hdr) ? substr($hdr, 0, 24) : null,
                'bearer_token_prefix' => is_string($bearer) ? substr($bearer, 0, 12) : null,
                'web_check_before' => Auth::guard('web')->check(),
            ]);
        }

        /**
         * API routes are protected by the default "auth" middleware (web guard),
         * but we often authenticate via Sanctum bearer tokens.
         *
         * If Sanctum guard already authenticated the user (e.g. via Authorization header),
         * mirror that user into the web guard so "auth" passes.
         */
        if (! Auth::guard('web')->check() && Auth::guard('sanctum')->check()) {
            $user = Auth::guard('sanctum')->user();
            if ($user) {
                Auth::guard('web')->setUser($user);
                $request->setUserResolver(static fn () => $user);
            }
        }

        // Сначала проверяем сессионную аутентификацию (web guard)
        // Это работает для веб-запросов, где пользователь залогинен через сессию
        if (! Auth::guard('web')->check() && ! Auth::guard('sanctum')->check()) {
            $token = $request->bearerToken();

            /**
             * Some nginx/FastCGI setups still don't expose Authorization as a "real" header to Symfony,
             * but do pass it via server params (e.g. HTTP_AUTHORIZATION / REDIRECT_HTTP_AUTHORIZATION).
             * For E2E and API usage we support both.
             */
            if (! $token) {
                $authHeader = $request->server('HTTP_AUTHORIZATION') ?: $request->server('REDIRECT_HTTP_AUTHORIZATION');
                if (is_string($authHeader) && str_starts_with($authHeader, 'Bearer ')) {
                    $token = substr($authHeader, 7);
                }
            }

            if ($token) {
                $accessToken = PersonalAccessToken::findToken($token);

                if ($accessToken && $accessToken->tokenable) {
                    // Проверяем срок действия токена
                    if ($accessToken->expires_at && $accessToken->expires_at->isPast()) {
                        \Log::warning('AuthenticateWithApiToken: Token expired', [
                            'token_id' => $accessToken->id,
                            'expires_at' => $accessToken->expires_at,
                        ]);

                        return response()->json([
                            'status' => 'error',
                            'code' => 'TOKEN_EXPIRED',
                            'message' => 'Token has expired',
                        ], 401);
                    }

                    // Проверяем abilities токена (если требуется)
                    // В будущем можно добавить проверку конкретных abilities для ограничения scope
                    // if ($accessToken->abilities && !in_array('required_ability', $accessToken->abilities)) {
                    //     return response()->json(['status' => 'error', 'message' => 'Token lacks required ability'], 403);
                    // }

                    $user = $accessToken->tokenable;
                    // Устанавливаем пользователя для обоих guard'ов
                    Auth::guard('web')->setUser($user);
                    Auth::guard('sanctum')->setUser($user);
                    $request->setUserResolver(static fn () => $user);

                    // Обновляем last_used_at для отслеживания активности токена
                    $accessToken->forceFill(['last_used_at' => now()])->save();
                    if (config('app.env') === 'testing' && str_starts_with($request->path(), 'api/zones')) {
                        Log::warning('AuthenticateWithApiToken(debug): zones authenticated via token', [
                            'user_id' => $user->id ?? null,
                            'token_id' => $accessToken->id ?? null,
                        ]);
                    }
                } else {
                    // Debug for E2E: token header exists but Sanctum cannot find it
                    if (config('app.env') === 'testing') {
                        Log::warning('AuthenticateWithApiToken: Bearer token present but not recognized by Sanctum', [
                            'token_prefix' => substr($token, 0, 12),
                            'has_pipe' => str_contains($token, '|'),
                            'path' => $request->path(),
                            'method' => $request->method(),
                            'has_authorization_header' => $request->headers->has('Authorization'),
                        ]);
                    }
                }
            } else {
                if (config('app.env') === 'testing') {
                    Log::warning('AuthenticateWithApiToken: no bearer token found on request', [
                        'path' => $request->path(),
                        'method' => $request->method(),
                        'has_authorization_header' => $request->headers->has('Authorization'),
                        'server_http_authorization' => (bool) $request->server('HTTP_AUTHORIZATION'),
                        'server_redirect_http_authorization' => (bool) $request->server('REDIRECT_HTTP_AUTHORIZATION'),
                    ]);
                }
            }
        }

        return $next($request);
    }
}
