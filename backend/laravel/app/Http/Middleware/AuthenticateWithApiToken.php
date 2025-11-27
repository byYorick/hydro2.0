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
                    $user = $accessToken->tokenable;
                    Auth::guard()->setUser($user);
                    $request->setUserResolver(static fn () => $user);
                }
            }
        }

        return $next($request);
    }
}
