<?php

namespace App\Http\Middleware;

use Closure;
use App\Models\SystemLog;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class AutomationEngineLegacySqlGuard
{
    /**
     * Legacy таблицы, которые должны быть удалены
     */
    protected const LEGACY_TABLES = [
        'zone_recipe_instances',
        'recipe_phases',
        'recipes',
    ];

    /**
     * Legacy колонки в существующих таблицах
     */
    protected const LEGACY_COLUMNS = [
        'grow_cycles.zone_recipe_instance_id',
        'grow_cycles.current_stage_code',
    ];

    /**
     * Пути Automation Engine, где guard активен
     */
    protected const AE_PATHS = [
        'api/zones/*/grow-cycles',
        'api/zones/*/grow-cycle',
        'api/zones/*/effective-targets',
        'api/zones/*/commands',
        'api/grow-cycles',
        'api/effective-targets',
    ];

    /**
     * Handle an incoming request.
     */
    public function handle(Request $request, Closure $next): Response
    {
        // Проверяем, относится ли запрос к Automation Engine
        if (!$this->isAutomationEngineRequest($request)) {
            return $next($request);
        }

        // Устанавливаем слушатель SQL запросов для логирования legacy доступа
        DB::listen(function ($query) {
            $this->checkLegacySqlAccess($query);
        });

        return $next($request);
    }

    /**
     * Проверяет, относится ли запрос к Automation Engine
     */
    protected function isAutomationEngineRequest(Request $request): bool
    {
        $path = $request->path();

        foreach (self::AE_PATHS as $aePath) {
            // Преобразуем wildcard пути в регулярные выражения
            $pattern = str_replace('*', '.*', $aePath);
            if (preg_match("#^{$pattern}#", $path)) {
                return true;
            }
        }

        return false;
    }

    /**
     * Проверяет SQL запрос на доступ к legacy таблицам/колонкам
     */
    protected function checkLegacySqlAccess($query): void
    {
        $sql = strtolower($query->sql);

        // Проверяем доступ к legacy таблицам
        foreach (self::LEGACY_TABLES as $table) {
            if (str_contains($sql, $table)) {
                $this->recordLegacyAccess('warning', 'AE_LEGACY_SQL_GUARD: Доступ к legacy таблице в Automation Engine', [
                    'table' => $table,
                    'sql' => $query->sql,
                    'bindings' => $query->bindings,
                    'time' => $query->time,
                    'trace' => $this->getFilteredTrace(),
                ]);
            }
        }

        // Проверяем доступ к legacy колонкам
        foreach (self::LEGACY_COLUMNS as $column) {
            if (str_contains($sql, $column)) {
                $this->recordLegacyAccess('error', 'AE_LEGACY_SQL_GUARD: Доступ к legacy колонке в Automation Engine', [
                    'column' => $column,
                    'sql' => $query->sql,
                    'bindings' => $query->bindings,
                    'time' => $query->time,
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
                'context' => array_merge(['service' => 'automation-engine'], $context),
                'created_at' => now(),
            ]);
        } catch (\Throwable $e) {
            Log::warning('AE_LEGACY_SQL_GUARD: Failed to persist system log', [
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Получить отфильтрованный stack trace (только релевантные фреймы)
     */
    protected function getFilteredTrace(): array
    {
        $trace = debug_backtrace(DEBUG_BACKTRACE_IGNORE_ARGS, 20);
        $filtered = [];

        foreach ($trace as $frame) {
            $file = $frame['file'] ?? '';

            // Фильтруем только релевантные фреймы (app/Services, app/Models, etc.)
            if (str_contains($file, 'app/Services') ||
                str_contains($file, 'app/Models') ||
                str_contains($file, 'app/Http/Controllers') ||
                str_contains($file, 'app/Jobs')) {
                $filtered[] = [
                    'file' => str_replace(base_path(), '', $file),
                    'line' => $frame['line'] ?? 0,
                    'class' => $frame['class'] ?? '',
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
