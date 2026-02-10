<?php

namespace Tests\Unit\Services;

use App\Services\ZoneEventMessageFormatter;
use Tests\TestCase;

class ZoneEventMessageFormatterTest extends TestCase
{
    private ZoneEventMessageFormatter $formatter;

    protected function setUp(): void
    {
        parent::setUp();

        $this->formatter = app(ZoneEventMessageFormatter::class);
    }

    public function test_format_returns_explicit_message_when_present(): void
    {
        $message = $this->formatter->format('ALERT_UPDATED', [
            'message' => 'Порог pH превышен',
            'code' => 'BIZ_HIGH_PH',
            'error_count' => 7,
        ]);

        $this->assertSame('Порог pH превышен', $message);
    }

    public function test_format_alert_updated_contains_code_and_repetition_count(): void
    {
        $message = $this->formatter->format('ALERT_UPDATED', [
            'code' => 'BIZ_HIGH_TEMP',
            'error_count' => 4,
        ]);

        $this->assertSame('Алерт BIZ_HIGH_TEMP обновлён (повторений: 4)', $message);
    }

    public function test_format_alert_created_contains_code_type_and_source(): void
    {
        $message = $this->formatter->format('ALERT_CREATED', [
            'code' => 'BIZ_NO_FLOW',
            'type' => 'NO_FLOW',
            'source' => 'biz',
        ]);

        $this->assertSame('Создан алерт BIZ_NO_FLOW (тип NO_FLOW, источник biz)', $message);
    }

    public function test_format_cycle_created_contains_core_identifiers(): void
    {
        $message = $this->formatter->format('CYCLE_CREATED', [
            'cycle_id' => 15,
            'recipe_revision_id' => 8,
            'plant_id' => 3,
            'source' => 'web',
        ]);

        $this->assertSame('Создан цикл: цикл #15, ревизия #8, растение #3, источник web', $message);
    }

    public function test_format_cycle_adjusted_with_subsystems_is_informative(): void
    {
        $message = $this->formatter->format('CYCLE_ADJUSTED', [
            'subsystems' => [
                'ph' => [
                    'enabled' => true,
                    'targets' => ['min' => 5.8, 'max' => 6.2],
                ],
                'ec' => [
                    'enabled' => true,
                    'targets' => ['min' => 1.3, 'max' => 1.7],
                ],
                'climate' => [
                    'enabled' => true,
                    'targets' => ['temperature' => 24.5, 'humidity' => 61],
                ],
                'lighting' => [
                    'enabled' => true,
                    'targets' => ['hours_on' => 18, 'hours_off' => 6],
                ],
                'irrigation' => [
                    'enabled' => true,
                    'targets' => ['interval_minutes' => 35, 'duration_seconds' => 70],
                ],
            ],
        ]);

        $this->assertSame(
            'Цикл скорректирован: pH 5.8–6.2; EC 1.3–1.7; Климат t=24.5°C, RH=61%; Свет 18.0ч / пауза 6.0ч; Полив каждые 35 мин, 70 с',
            $message
        );
    }

    public function test_format_cycle_aborted_includes_reason(): void
    {
        $message = $this->formatter->format('CYCLE_ABORTED', [
            'reason' => 'Emergency stop by safety watchdog',
        ]);

        $this->assertSame('Цикл аварийно остановлен: Emergency stop by safety watchdog', $message);
    }

    public function test_format_recipe_revision_change_includes_mode(): void
    {
        $message = $this->formatter->format('CYCLE_RECIPE_REVISION_CHANGED', [
            'from_revision_id' => 12,
            'to_revision_id' => 13,
            'apply_mode' => 'next_phase',
        ]);

        $this->assertSame('Смена ревизии рецепта: #12 -> #13 (со следующей фазы)', $message);
    }

    public function test_format_phase_transition_is_human_readable(): void
    {
        $message = $this->formatter->format('PHASE_TRANSITION', [
            'from_phase' => 2,
            'to_phase' => 3,
        ]);

        $this->assertSame('Смена фазы: #2 -> #3', $message);
    }

    public function test_format_zone_command_contains_operator_context(): void
    {
        $message = $this->formatter->format('ZONE_COMMAND', [
            'command_type' => 'FORCE_IRRIGATION',
            'node_uid' => 'node-77',
            'channel' => 'pump_main',
            'user_name' => 'operator@hydro',
        ]);

        $this->assertSame(
            'Команда зоны: FORCE_IRRIGATION (нода node-77, канал pump_main, пользователь operator@hydro)',
            $message
        );
    }
}
