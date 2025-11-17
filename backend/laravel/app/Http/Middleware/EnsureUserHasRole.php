<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class EnsureUserHasRole
{
    public function handle(Request $request, Closure $next, string ...$roles): Response
    {
        $user = $request->user();
        if (!$user) {
            abort(401);
        }
        if (empty($roles)) {
            return $next($request);
        }
        if (!in_array($user->role ?? 'viewer', $roles, true)) {
            abort(403);
        }
        return $next($request);
    }
}

