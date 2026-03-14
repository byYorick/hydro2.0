<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\Cache;

class SystemAutomationSetting extends Model
{
    use HasFactory;

    protected $fillable = [
        'namespace',
        'config',
        'updated_by',
    ];

    protected $casts = [
        'config' => 'array',
    ];

    public static function forNamespace(string $namespace): array
    {
        return Cache::remember(
            "system_automation_settings:{$namespace}",
            300,
            static function () use ($namespace): array {
                $config = static::query()
                    ->where('namespace', $namespace)
                    ->value('config');

                if (! is_array($config)) {
                    throw new \RuntimeException(
                        "system_automation_settings namespace '{$namespace}' not found"
                    );
                }

                return $config;
            }
        );
    }

    public static function flushCache(string $namespace): void
    {
        Cache::forget("system_automation_settings:{$namespace}");
    }

    protected static function booted(): void
    {
        static::saved(function (self $setting): void {
            self::flushCache($setting->namespace);
        });

        static::deleted(function (self $setting): void {
            self::flushCache($setting->namespace);
        });
    }
}
