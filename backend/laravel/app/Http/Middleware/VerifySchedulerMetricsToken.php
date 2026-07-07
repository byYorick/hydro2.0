<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Config;
use Symfony\Component\HttpFoundation\Response;

class VerifySchedulerMetricsToken
{
    public function handle(Request $request, Closure $next): Response
    {
        $expectedToken = Config::get('services.automation_engine.scheduler_metrics_token');
        if (! is_string($expectedToken) || trim($expectedToken) === '') {
            return $next($request);
        }

        $providedToken = $request->bearerToken();
        if (is_string($providedToken) && hash_equals($expectedToken, $providedToken)) {
            return $next($request);
        }

        return response('Unauthorized', 401, [
            'Content-Type' => 'text/plain; charset=utf-8',
        ]);
    }
}
