<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        $correctionPresetIds = DB::table('automation_config_presets')
            ->where('namespace', 'zone.correction')
            ->where('scope', 'system')
            ->pluck('id', 'slug');

        $now = now();

        $presets = [
            // ── Drip Tape Safe ──
            [
                'name' => 'Drip Tape Safe',
                'slug' => 'drip-tape-safe',
                'description' => "Консервативный профиль для капельного полива.\n\n"
                    ."Мягкие дозы коррекции, увеличенные интервалы и таймауты. "
                    ."Подходит для первого запуска капельной системы, чувствительных культур "
                    ."и при неуверенности в калибровке насосов.\n\n"
                    ."• Интервал полива: 90 мин, длительность: 3 мин\n"
                    ."• Коррекция pH/EC во время полива: нет\n"
                    ."• Увеличенный slack: 90 сек\n"
                    ."• Таймаут заполнения чистой воды: 25 мин\n"
                    ."• Таймаут заполнения раствора: 40 мин\n"
                    ."• Таймаут рециркуляции: 25 мин\n\n"
                    ."Рекомендуется для новых капельных систем и первого запуска.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'drip_tape',
                'correction_preset_id' => $correctionPresetIds['safe'] ?? null,
                'correction_profile' => 'safe',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 180,
                        'interval_sec' => 5400,
                        'correction_during_irrigation' => false,
                        'correction_slack_sec' => 90,
                    ],
                    'irrigation_decision' => ['strategy' => 'task'],
                    'startup' => [
                        'clean_fill_timeout_sec' => 1500,
                        'solution_fill_timeout_sec' => 2400,
                        'prepare_recirculation_timeout_sec' => 1500,
                        'level_poll_interval_sec' => 60,
                        'clean_fill_retry_cycles' => 1,
                    ],
                    'climate' => null,
                    'lighting' => null,
                ], JSON_UNESCAPED_UNICODE),
            ],
            // ── Drip Tape Aggressive ──
            [
                'name' => 'Drip Tape Aggressive',
                'slug' => 'drip-tape-aggressive',
                'description' => "Быстрый профиль для откалиброванных капельных систем.\n\n"
                    ."Агрессивная коррекция с укороченными таймаутами. "
                    ."Позволяет быстрее достичь целевых pH/EC.\n\n"
                    ."• Интервал полива: 60 мин, длительность: 3 мин\n"
                    ."• Коррекция pH/EC во время полива: нет\n"
                    ."• Минимальный slack: 30 сек\n"
                    ."• Таймаут заполнения чистой воды: 15 мин\n"
                    ."• Таймаут заполнения раствора: 20 мин\n"
                    ."• Таймаут рециркуляции: 15 мин\n\n"
                    ."⚠ Только для опытных пользователей с проверенной калибровкой.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'drip_tape',
                'correction_preset_id' => $correctionPresetIds['aggressive'] ?? null,
                'correction_profile' => 'aggressive',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 180,
                        'interval_sec' => 3600,
                        'correction_during_irrigation' => false,
                        'correction_slack_sec' => 30,
                    ],
                    'irrigation_decision' => ['strategy' => 'task'],
                    'startup' => [
                        'clean_fill_timeout_sec' => 900,
                        'solution_fill_timeout_sec' => 1200,
                        'prepare_recirculation_timeout_sec' => 900,
                        'level_poll_interval_sec' => 45,
                        'clean_fill_retry_cycles' => 1,
                    ],
                    'climate' => null,
                    'lighting' => null,
                ], JSON_UNESCAPED_UNICODE),
            ],
            // ── NFT Safe ──
            [
                'name' => 'NFT Safe',
                'slug' => 'nft-safe',
                'description' => "Консервативный профиль для NFT системы.\n\n"
                    ."Мягкие дозы коррекции, увеличенное время стабилизации. "
                    ."Раствор циркулирует непрерывно, коррекция включена, но дозы минимальные.\n\n"
                    ."• Интервал полива: 30 мин, длительность: 15 мин\n"
                    ."• Коррекция pH/EC во время полива: да\n"
                    ."• Увеличенный slack: 30 сек\n"
                    ."• Таймаут заполнения чистой воды: 25 мин\n"
                    ."• Таймаут заполнения раствора: 40 мин\n"
                    ."• Таймаут рециркуляции: 25 мин\n\n"
                    ."Рекомендуется для первого запуска NFT и чувствительных культур.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'nft',
                'correction_preset_id' => $correctionPresetIds['safe'] ?? null,
                'correction_profile' => 'safe',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 900,
                        'interval_sec' => 1800,
                        'correction_during_irrigation' => true,
                        'correction_slack_sec' => 30,
                    ],
                    'irrigation_decision' => ['strategy' => 'task'],
                    'startup' => [
                        'clean_fill_timeout_sec' => 1500,
                        'solution_fill_timeout_sec' => 2400,
                        'prepare_recirculation_timeout_sec' => 1500,
                        'level_poll_interval_sec' => 60,
                        'clean_fill_retry_cycles' => 1,
                    ],
                    'climate' => null,
                    'lighting' => null,
                ], JSON_UNESCAPED_UNICODE),
            ],
            // ── NFT Aggressive ──
            [
                'name' => 'NFT Aggressive',
                'slug' => 'nft-aggressive',
                'description' => "Быстрый профиль для откалиброванных NFT систем.\n\n"
                    ."Агрессивная коррекция, укороченные таймауты. "
                    ."Раствор постоянно циркулирует — быстрый отклик системы.\n\n"
                    ."• Интервал полива: 20 мин, длительность: 15 мин\n"
                    ."• Коррекция pH/EC во время полива: да\n"
                    ."• Минимальный slack: 10 сек\n"
                    ."• Таймаут заполнения чистой воды: 15 мин\n"
                    ."• Таймаут заполнения раствора: 20 мин\n"
                    ."• Таймаут рециркуляции: 15 мин\n\n"
                    ."⚠ Только для опытных пользователей с проверенной калибровкой.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'nft',
                'correction_preset_id' => $correctionPresetIds['aggressive'] ?? null,
                'correction_profile' => 'aggressive',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 900,
                        'interval_sec' => 1200,
                        'correction_during_irrigation' => true,
                        'correction_slack_sec' => 10,
                    ],
                    'irrigation_decision' => ['strategy' => 'task'],
                    'startup' => [
                        'clean_fill_timeout_sec' => 900,
                        'solution_fill_timeout_sec' => 1200,
                        'prepare_recirculation_timeout_sec' => 900,
                        'level_poll_interval_sec' => 45,
                        'clean_fill_retry_cycles' => 1,
                    ],
                    'climate' => null,
                    'lighting' => null,
                ], JSON_UNESCAPED_UNICODE),
            ],
        ];

        foreach ($presets as $preset) {
            DB::table('zone_automation_presets')->insert(array_merge($preset, [
                'created_at' => $now,
                'updated_at' => $now,
            ]));
        }
    }

    public function down(): void
    {
        DB::table('zone_automation_presets')
            ->whereIn('slug', [
                'drip-tape-safe',
                'drip-tape-aggressive',
                'nft-safe',
                'nft-aggressive',
            ])
            ->delete();
    }
};
