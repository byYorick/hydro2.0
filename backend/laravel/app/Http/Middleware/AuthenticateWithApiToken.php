<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Laravel\Sanctum\PersonalAccessToken;

class AuthenticateWithApiToken
{
    /**
     * Attempt to authenticate the incoming request using a Sanctum personal access token.
     * Falls back to the default session guard so the existing 'auth' middleware can pass.
     */
    public function handle(Request $request, Closure $next)
    {
        // Сначала проверяем сессионную аутентификацию (web guard)
        // Это работает для веб-запросов, где пользователь залогинен через сессию
        if (! Auth::guard('web')->check() && ! Auth::guard('sanctum')->check()) {
            $token = $request->bearerToken();

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
                }
            }
        }

        return $next($request);
    }
}
