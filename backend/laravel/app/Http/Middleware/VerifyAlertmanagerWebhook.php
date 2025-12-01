<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class VerifyAlertmanagerWebhook
{
    /**
     * Handle an incoming request.
     *
     * Проверяет секрет/токен для вебхука Alertmanager.
     * Поддерживает два метода:
     * 1. Bearer token в заголовке Authorization
     * 2. Секрет в заголовке X-Webhook-Secret
     * 3. Basic Auth (username игнорируется, password используется как секрет)
     */
    public function handle(Request $request, Closure $next): Response
    {
        $expectedSecret = Config::get('services.alertmanager.webhook_secret');
        
        // Если секрет не настроен, разрешаем доступ только в dev/testing окружении
        if (!$expectedSecret) {
            $env = config('app.env');
            if (in_array($env, ['local', 'testing', 'dev'])) {
                Log::warning('Alertmanager webhook secret not configured, allowing access in dev mode', [
                    'url' => $request->fullUrl(),
                    'ip' => $request->ip(),
                ]);
                return $next($request);
            }
            
            Log::error('Alertmanager webhook secret not configured', [
                'url' => $request->fullUrl(),
                'ip' => $request->ip(),
                'env' => $env,
            ]);
            return response()->json([
                'status' => 'error',
                'message' => 'Webhook authentication not configured',
            ], 500);
        }

        // Проверяем Bearer token
        $bearerToken = $request->bearerToken();
        if ($bearerToken && hash_equals($expectedSecret, $bearerToken)) {
            Log::debug('Alertmanager webhook authenticated via Bearer token');
            return $next($request);
        }

        // Проверяем заголовок X-Webhook-Secret
        $webhookSecret = $request->header('X-Webhook-Secret');
        if ($webhookSecret && hash_equals($expectedSecret, $webhookSecret)) {
            Log::debug('Alertmanager webhook authenticated via X-Webhook-Secret header');
            return $next($request);
        }

        // Проверяем Basic Auth
        $authHeader = $request->header('Authorization');
        if ($authHeader && str_starts_with($authHeader, 'Basic ')) {
            $credentials = base64_decode(substr($authHeader, 6));
            if ($credentials !== false) {
                [$username, $password] = explode(':', $credentials, 2) + ['', ''];
                if (hash_equals($expectedSecret, $password)) {
                    Log::debug('Alertmanager webhook authenticated via Basic Auth');
                    return $next($request);
                }
            }
        }

        // Проверяем IP-адрес источника (опционально, если настроен список разрешенных IP)
        $allowedIps = Config::get('services.alertmanager.allowed_ips', []);
        if (!empty($allowedIps) && is_array($allowedIps)) {
            $clientIp = $request->ip();
            // Проверяем точное совпадение или подсеть
            foreach ($allowedIps as $allowedIp) {
                if ($clientIp === $allowedIp || 
                    (str_contains($allowedIp, '/') && $this->ipInRange($clientIp, $allowedIp))) {
                    Log::debug('Alertmanager webhook authenticated via IP whitelist', [
                        'ip' => $clientIp,
                    ]);
                    return $next($request);
                }
            }
        }

        // Все проверки не прошли
        Log::warning('Alertmanager webhook authentication failed', [
            'url' => $request->fullUrl(),
            'ip' => $request->ip(),
            'user_agent' => $request->userAgent(),
            'has_bearer' => !empty($bearerToken),
            'has_webhook_secret' => !empty($webhookSecret),
            'has_basic_auth' => !empty($authHeader) && str_starts_with($authHeader, 'Basic '),
        ]);

        return response()->json([
            'status' => 'error',
            'message' => 'Unauthorized: invalid webhook secret or IP not allowed',
        ], 401);
    }

    /**
     * Проверяет, находится ли IP в указанном диапазоне (CIDR)
     */
    private function ipInRange(string $ip, string $range): bool
    {
        if (!str_contains($range, '/')) {
            return false;
        }

        [$subnet, $mask] = explode('/', $range, 2);
        
        if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
            $ipLong = ip2long($ip);
            $subnetLong = ip2long($subnet);
            $maskLong = -1 << (32 - (int)$mask);
            return ($ipLong & $maskLong) === ($subnetLong & $maskLong);
        }

        if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) {
            // Упрощенная проверка для IPv6 (можно улучшить)
            return inet_pton($ip) && inet_pton($subnet);
        }

        return false;
    }
}

