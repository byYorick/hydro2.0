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
        if (! Auth::check()) {
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
                    Auth::guard()->setUser($user);
                    $request->setUserResolver(static fn () => $user);
                    
                    // Обновляем last_used_at для отслеживания активности токена
                    $accessToken->forceFill(['last_used_at' => now()])->save();
                }
            }
        }

        return $next($request);
    }
}
