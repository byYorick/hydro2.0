<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

/**
 * Проверяет HMAC-SHA256 подпись входящего webhook от history-logger-а.
 *
 * Ожидаемые заголовки:
 *   X-Hydro-Signature: hex(hmac_sha256(secret, raw_body))
 *   X-Hydro-Timestamp: unix-time (±300 секунд, replay protection)
 *
 * Secret: `services.history_logger.webhook_secret` (env: HISTORY_LOGGER_WEBHOOK_SECRET).
 */
class VerifyHistoryLoggerWebhook
{
    private const MAX_CLOCK_SKEW_SEC = 300;

    public function handle(Request $request, Closure $next): Response
    {
        $secret = (string) Config::get('services.history_logger.webhook_secret', '');

        if ($secret === '') {
            $env = (string) config('app.env');
            if (in_array($env, ['local', 'testing', 'dev'], true)) {
                Log::warning('history-logger webhook secret not configured; allowing in dev', [
                    'ip' => $request->ip(),
                ]);

                return $next($request);
            }

            Log::error('history-logger webhook secret not configured in production env', [
                'ip' => $request->ip(),
                'env' => $env,
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Webhook authentication not configured',
            ], 500);
        }

        $signature = trim((string) $request->header('X-Hydro-Signature', ''));
        $timestampHeader = trim((string) $request->header('X-Hydro-Timestamp', ''));

        if ($signature === '' || $timestampHeader === '' || ! ctype_digit($timestampHeader)) {
            Log::warning('history-logger webhook missing signature/timestamp', [
                'ip' => $request->ip(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: missing signature headers',
            ], 401);
        }

        $timestamp = (int) $timestampHeader;
        $now = time();
        if (abs($now - $timestamp) > self::MAX_CLOCK_SKEW_SEC) {
            Log::warning('history-logger webhook timestamp out of window', [
                'ip' => $request->ip(),
                'skew_sec' => $now - $timestamp,
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: timestamp skew',
            ], 401);
        }

        $rawBody = (string) $request->getContent();
        $expected = hash_hmac('sha256', $timestampHeader.'.'.$rawBody, $secret);

        if (! hash_equals($expected, strtolower($signature))) {
            Log::warning('history-logger webhook signature mismatch', [
                'ip' => $request->ip(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized: signature mismatch',
            ], 401);
        }

        return $next($request);
    }
}
