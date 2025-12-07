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
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        if (empty($roles)) {
            return $next($request);
        }
        if (!in_array($user->role ?? 'viewer', $roles, true)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden',
            ], 403);
        }
        return $next($request);
    }
}
