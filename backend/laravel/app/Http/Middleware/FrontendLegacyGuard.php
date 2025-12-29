<?php

namespace App\Http\Middleware;

use Closure;
use App\Models\SystemLog;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class FrontendLegacyGuard
{
    /**
     * Legacy паттерны в URL, которые могут указывать на использование legacy данных
     */
    protected const LEGACY_URL_PATTERNS = [
        'zone-recipe-instances',
        'recipe-phases',
        'legacy-',
        'old-',
    ];

    /**
     * Legacy параметры запроса, которые не должны использоваться
     */
    protected const LEGACY_QUERY_PARAMS = [
        'zone_recipe_instance_id',
        'current_stage_code',
        'legacy_mode',
        'old_format',
    ];

    /**
     * Handle an incoming request.
     */
    public function handle(Request $request, Closure $next): Response
    {
        // Проверяем только для веб-запросов (не API)
        if ($request->is('api/*')) {
            return $next($request);
        }

        $this->checkLegacyUrlPatterns($request);
        $this->checkLegacyQueryParams($request);

        return $next($request);
    }

    /**
     * Проверяет URL на наличие legacy паттернов
     */
    protected function checkLegacyUrlPatterns(Request $request): void
    {
        $url = $request->fullUrl();
        $path = $request->path();

        foreach (self::LEGACY_URL_PATTERNS as $pattern) {
            if (str_contains($url, $pattern) || str_contains($path, $pattern)) {
                $this->recordLegacyAccess('warning', 'FRONT_LEGACY_GUARD: Legacy URL pattern detected', [
                    'url' => $url,
                    'path' => $path,
                    'pattern' => $pattern,
                    'user_id' => auth()->id(),
                    'ip' => $request->ip(),
                    'user_agent' => $request->userAgent(),
                    'trace' => $this->getFilteredTrace(),
                ]);
            }
        }
    }

    /**
     * Проверяет query параметры на наличие legacy параметров
     */
    protected function checkLegacyQueryParams(Request $request): void
    {
        $queryParams = $request->query();

        foreach (self::LEGACY_QUERY_PARAMS as $param) {
            if ($request->has($param)) {
                $this->recordLegacyAccess('error', 'FRONT_LEGACY_GUARD: Legacy query parameter detected', [
                    'url' => $request->fullUrl(),
                    'param' => $param,
                    'value' => $request->query($param),
                    'all_params' => $queryParams,
                    'user_id' => auth()->id(),
                    'ip' => $request->ip(),
                    'user_agent' => $request->userAgent(),
                    'trace' => $this->getFilteredTrace(),
                ]);
            }
        }
    }

    protected function recordLegacyAccess(string $level, string $message, array $context): void
    {
        Log::log($level, $message, $context);

        try {
            SystemLog::create([
                'level' => $level,
                'message' => $message,
                'context' => array_merge(['service' => 'frontend'], $context),
                'created_at' => now(),
            ]);
        } catch (\Throwable $e) {
            Log::warning('FRONT_LEGACY_GUARD: Failed to persist system log', [
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Получить отфильтрованный stack trace
     */
    protected function getFilteredTrace(): array
    {
        $trace = debug_backtrace(DEBUG_BACKTRACE_IGNORE_ARGS, 15);
        $filtered = [];

        foreach ($trace as $frame) {
            $file = $frame['file'] ?? '';

            // Фильтруем только релевантные фреймы (frontend routes, controllers, etc.)
            if (str_contains($file, 'routes/web.php') ||
                str_contains($file, 'resources/js') ||
                str_contains($file, 'Http/Controllers') ||
                str_contains($file, 'routes/') && !str_contains($file, 'api.php')) {
                $filtered[] = [
                    'file' => str_replace(base_path(), '', $file),
                    'line' => $frame['line'] ?? 0,
                    'function' => $frame['function'] ?? '',
                ];
            }

            // Ограничиваем до 5 фреймов
            if (count($filtered) >= 5) {
                break;
            }
        }

        return $filtered;
    }
}
