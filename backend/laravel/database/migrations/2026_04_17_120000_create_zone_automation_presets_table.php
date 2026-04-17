<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('zone_automation_presets', function (Blueprint $table): void {
            $table->id();
            $table->string('name', 128);
            $table->string('slug', 128)->unique();
            $table->text('description')->nullable();
            $table->string('scope', 16)->default('custom');
            $table->boolean('is_locked')->default(false);

            // Фильтры совместимости
            $table->smallInteger('tanks_count')->default(2);
            $table->string('irrigation_system_type', 32)->default('dwc');

            // Ссылка на секционный пресет коррекции
            $table->foreignId('correction_preset_id')
                ->nullable()
                ->constrained('automation_config_presets')
                ->nullOnDelete();
            $table->string('correction_profile', 32)->nullable();

            // Inline конфиг секций
            $table->jsonb('config')->default(DB::raw("'{}'::jsonb"));

            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('updated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();

            $table->index('scope', 'zone_automation_presets_scope_idx');
            $table->index(['tanks_count', 'irrigation_system_type'], 'zone_automation_presets_compat_idx');
        });

        $this->seedSystemPresets();
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_automation_presets');
    }

    private function seedSystemPresets(): void
    {
        $correctionPresetIds = DB::table('automation_config_presets')
            ->where('namespace', 'zone.correction')
            ->where('scope', 'system')
            ->pluck('id', 'slug');

        $now = now();

        $presets = [
            [
                'name' => 'DWC Balanced',
                'slug' => 'dwc-balanced',
                'description' => "Стандартный профиль для DWC системы с двумя баками.\n\n"
                    ."Оптимальный баланс между скоростью коррекции и стабильностью раствора. "
                    ."Подходит для большинства культур в установившемся режиме работы.\n\n"
                    ."• Интервал полива: 60 мин, длительность: 5 мин\n"
                    ."• Коррекция pH/EC во время полива: да\n"
                    ."• Таймаут заполнения чистой воды: 20 м��н\n"
                    ."• Таймаут заполнения раствора: 30 мин\n"
                    ."• Таймаут рециркуляции: 20 мин\n\n"
                    ."Рекомендуется как стартовый профиль для новых зон.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'dwc',
                'correction_preset_id' => $correctionPresetIds['balanced'] ?? null,
                'correction_profile' => 'balanced',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 300,
                        'interval_sec' => 3600,
                        'correction_during_irrigation' => true,
                        'correction_slack_sec' => 30,
                    ],
                    'irrigation_decision' => [
                        'strategy' => 'task',
                    ],
                    'startup' => [
                        'clean_fill_timeout_sec' => 1200,
                        'solution_fill_timeout_sec' => 1800,
                        'prepare_recirculation_timeout_sec' => 1200,
                        'level_poll_interval_sec' => 60,
                        'clean_fill_retry_cycles' => 1,
                    ],
                    'climate' => null,
                    'lighting' => null,
                ], JSON_UNESCAPED_UNICODE),
            ],
            [
                'name' => 'DWC Safe',
                'slug' => 'dwc-safe',
                'description' => "Консервативный профиль для DWC системы.\n\n"
                    ."Мягкие дозы, увеличенное время стабилизации между дозированиями. "
                    ."Минимальный риск ухода pH/EC за безопасные границы.\n\n"
                    ."• Интервал полива: 60 мин, длительность: 5 мин\n"
                    ."• Увеличенный slack между коррекцией и поливом: 45 сек\n"
                    ."• Таймаут заполнения чистой воды: 25 мин\n"
                    ."• Таймаут заполнения раствора: 40 мин\n"
                    ."• Таймаут рециркуляции: 25 мин\n\n"
                    ."Рекомендуется для первого запуска новой системы, чувствительных культур "
                    ."(салат, микрозелень) и при неуверенности в калибровке насосов.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'dwc',
                'correction_preset_id' => $correctionPresetIds['safe'] ?? null,
                'correction_profile' => 'safe',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 300,
                        'interval_sec' => 3600,
                        'correction_during_irrigation' => true,
                        'correction_slack_sec' => 45,
                    ],
                    'irrigation_decision' => [
                        'strategy' => 'task',
                    ],
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
            [
                'name' => 'DWC Aggressive',
                'slug' => 'dwc-aggressive',
                'description' => "Быстрый профиль для хорошо откалиброванных DWC систем.\n\n"
                    ."Высокие дозы, минимальная стабилизация. Позволяет быстрее выйти "
                    ."на целевые значения pH/EC за счёт более агрессивной коррекции.\n\n"
                    ."• Интервал полива: 60 мин, длительность: 5 мин\n"
                    ."• Минимальный slack: 15 сек\n"
                    ."• Таймаут заполнения чистой воды: 15 мин\n"
                    ."• Таймаут заполнения раствора: 20 мин\n"
                    ."• Таймаут рециркуляции: 15 мин\n\n"
                    ."⚠ Только для опытных пользователей с проверенной калибровкой насосов. "
                    ."При неточной калибровке возможен перелёт pH/EC за целевые значения.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'dwc',
                'correction_preset_id' => $correctionPresetIds['aggressive'] ?? null,
                'correction_profile' => 'aggressive',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 300,
                        'interval_sec' => 3600,
                        'correction_during_irrigation' => true,
                        'correction_slack_sec' => 15,
                    ],
                    'irrigation_decision' => [
                        'strategy' => 'task',
                    ],
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
            [
                'name' => 'Drip Tape Balanced',
                'slug' => 'drip-tape-balanced',
                'description' => "Стандартный профиль для капельного полива (drip tape).\n\n"
                    ."Двухбаковая система с оптимальными параметрами. Интервал полива увеличен "
                    ."с учётом времени доставки раствора по капельным линиям.\n\n"
                    ."• Интервал полива: 90 мин, длительность: 3 мин\n"
                    ."• Коррекция pH/EC во время полива: нет (раствор в линиях)\n"
                    ."• Увеличенный slack: 60 сек (стабилизация после возврата)\n"
                    ."• Таймаут заполнения чистой воды: 20 мин\n"
                    ."• Таймаут заполнения раствора: 30 мин\n\n"
                    ."Подходит для систем с капельными лентами и эмиттерами.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'drip_tape',
                'correction_preset_id' => $correctionPresetIds['balanced'] ?? null,
                'correction_profile' => 'balanced',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 180,
                        'interval_sec' => 5400,
                        'correction_during_irrigation' => false,
                        'correction_slack_sec' => 60,
                    ],
                    'irrigation_decision' => [
                        'strategy' => 'task',
                    ],
                    'startup' => [
                        'clean_fill_timeout_sec' => 1200,
                        'solution_fill_timeout_sec' => 1800,
                        'prepare_recirculation_timeout_sec' => 1200,
                        'level_poll_interval_sec' => 60,
                        'clean_fill_retry_cycles' => 1,
                    ],
                    'climate' => null,
                    'lighting' => null,
                ], JSON_UNESCAPED_UNICODE),
            ],
            [
                'name' => 'NFT Balanced',
                'slug' => 'nft-balanced',
                'description' => "Стандартный профиль для NFT (Nutrient Film Technique).\n\n"
                    ."Непрерывная тонкая плёнка питательного раствора. Короткий интервал "
                    ."между подачами, коррекция во время полива включена — раствор "
                    ."постоянно циркулирует через корневую зону.\n\n"
                    ."• Интервал полива: 30 мин, длительность: 15 мин\n"
                    ."�� Коррекция pH/EC во время полива: да\n"
                    ."• Минимальный slack: 15 сек\n"
                    ."• Таймаут заполнения чистой воды: 20 мин\n"
                    ."• Таймаут заполнения раствора: 30 мин\n\n"
                    ."Подходит для NFT-каналов с постоянной рециркуляцией.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'nft',
                'correction_preset_id' => $correctionPresetIds['balanced'] ?? null,
                'correction_profile' => 'balanced',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 900,
                        'interval_sec' => 1800,
                        'correction_during_irrigation' => true,
                        'correction_slack_sec' => 15,
                    ],
                    'irrigation_decision' => [
                        'strategy' => 'task',
                    ],
                    'startup' => [
                        'clean_fill_timeout_sec' => 1200,
                        'solution_fill_timeout_sec' => 1800,
                        'prepare_recirculation_timeout_sec' => 1200,
                        'level_poll_interval_sec' => 60,
                        'clean_fill_retry_cycles' => 1,
                    ],
                    'climate' => null,
                    'lighting' => null,
                ], JSON_UNESCAPED_UNICODE),
            ],
            [
                'name' => 'Test Node',
                'slug' => 'test-node-automation',
                'description' => "Профиль для тестовой ноды и HIL-тестирования.\n\n"
                    ."Малый объём раствора, мягкие дозы, сокращённые таймауты. "
                    ."Позволяет быстро проверить весь цикл автоматики без ожидания "
                    ."реальных таймаутов production-систем.\n\n"
                    ."• Интервал полива: 30 мин, длительность: 2 мин\n"
                    ."• Коррекция pH/EC во время полива: да\n"
                    ."• Таймаут заполнения чистой воды: 10 мин\n"
                    ."• Таймаут заполнения раствора: 10 мин\n"
                    ."• Опрос уровня: каждые 30 сек\n\n"
                    ."⚠ Не для production. Используется при разработке и отладке.",
                'scope' => 'system',
                'is_locked' => true,
                'tanks_count' => 2,
                'irrigation_system_type' => 'dwc',
                'correction_preset_id' => $correctionPresetIds['test-node'] ?? null,
                'correction_profile' => 'test',
                'config' => json_encode([
                    'irrigation' => [
                        'duration_sec' => 120,
                        'interval_sec' => 1800,
                        'correction_during_irrigation' => true,
                        'correction_slack_sec' => 15,
                    ],
                    'irrigation_decision' => [
                        'strategy' => 'task',
                    ],
                    'startup' => [
                        'clean_fill_timeout_sec' => 600,
                        'solution_fill_timeout_sec' => 600,
                        'prepare_recirculation_timeout_sec' => 600,
                        'level_poll_interval_sec' => 30,
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
};
