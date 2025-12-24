<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class NodeRegistrationIpWhitelist
{
    /**
     * Handle an incoming request.
     *
     * @param  \Illuminate\Http\Request  $request
     * @param  \Closure  $next
     * @return mixed
     */
    public function handle(Request $request, Closure $next)
    {
        // Пропускаем проверку в тестовом окружении
        if (app()->environment('testing')) {
            return $next($request);
        }

        $allowedIps = config('services.node_registration.allowed_ips', []);
        $clientIp = $request->ip();

        // Если список разрешенных IP пуст, пропускаем проверку
        if (empty($allowedIps) || !is_array($allowedIps)) {
            Log::debug('NodeRegistrationIpWhitelist: No allowed IPs configured, skipping whitelist check.');
            return $next($request);
        }

        // Проверяем, находится ли IP клиента в списке разрешенных (поддержка CIDR)
        if ($this->isIpAllowed($clientIp, $allowedIps)) {
            Log::debug('NodeRegistrationIpWhitelist: Client IP is whitelisted.', ['ip' => $clientIp]);
            return $next($request);
        }

        Log::warning('NodeRegistrationIpWhitelist: Client IP not in whitelist, access denied.', ['ip' => $clientIp]);

        return response()->json([
            'status' => 'error',
            'message' => 'Access denied: Your IP address is not whitelisted for node registration.',
        ], 403);
    }

    /**
     * Проверить, разрешен ли IP адрес.
     *
     * @param string $ip
     * @param array $allowedRanges Массив CIDR нотаций или IP адресов
     * @return bool
     */
    private function isIpAllowed(string $ip, array $allowedRanges): bool
    {
        foreach ($allowedRanges as $range) {
            if ($this->ipInRange($ip, $range)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Проверить, находится ли IP в диапазоне.
     *
     * @param string $ip
     * @param string $range CIDR нотация (например, "192.168.1.0/24") или точный IP
     * @return bool
     */
    private function ipInRange(string $ip, string $range): bool
    {
        // Если это точный IP адрес
        if (filter_var($range, FILTER_VALIDATE_IP)) {
            return $ip === $range;
        }

        // Если это CIDR нотация
        if (str_contains($range, '/')) {
            list($subnet, $mask) = explode('/', $range);
            
            if (!filter_var($subnet, FILTER_VALIDATE_IP)) {
                return false;
            }

            $ipLong = ip2long($ip);
            $subnetLong = ip2long($subnet);
            
            if ($ipLong === false || $subnetLong === false) {
                return false;
            }

            $maskLong = -1 << (32 - (int)$mask);
            return ($ipLong & $maskLong) === ($subnetLong & $maskLong);
        }

        return false;
    }
}

