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

    public function test_format_water_level_low_contains_level_and_threshold(): void
    {
        $message = $this->formatter->format('WATER_LEVEL_LOW', [
            'level' => 0.0,
            'threshold' => 0.2,
        ]);

        $this->assertSame('Низкий уровень воды (уровень 0.0%, порог 20.0%)', $message);
    }

    public function test_format_alert_created_for_water_level_contains_context(): void
    {
        $message = $this->formatter->format('ALERT_CREATED', [
            'alert_type' => 'WATER_LEVEL_LOW',
            'level' => 0.1,
            'threshold' => 0.2,
        ]);

        $this->assertSame('Создан алерт WATER_LEVEL_LOW (уровень 10.0%, порог 20.0%)', $message);
    }

    public function test_format_schedule_task_failed_contains_reason_and_identifiers(): void
    {
        $message = $this->formatter->format('SCHEDULE_TASK_FAILED', [
            'task_type' => 'diagnostics',
            'reason' => 'submit_failed',
            'correlation_id' => 'ae:self:5:diagnostics:enq-123',
        ]);

        $this->assertSame(
            'Scheduler: задача диагностики завершилась с ошибкой (причина: не удалось отправить задачу, корреляция: ae:self:5:diagnostics:enq-123)',
            $message
        );
    }

    public function test_format_irrigation_decision_snapshot_locked_contains_bundle_revision_prefix(): void
    {
        $message = $this->formatter->format('IRRIGATION_DECISION_SNAPSHOT_LOCKED', [
            'strategy' => 'schedule',
            'bundle_revision' => '1234567890abcdef1234567890abcdef12345678',
        ]);

        $this->assertSame(
            'Снимок decision-controller полива зафиксирован: schedule (1234567890ab)',
            $message
        );
    }

    public function test_format_irrigation_decision_evaluated_degraded_run_is_human_readable(): void
    {
        $message = $this->formatter->format('IRRIGATION_DECISION_EVALUATED', [
            'strategy' => 'smart_soil_v1',
            'outcome' => 'degraded_run',
            'reason_code' => 'smart_soil_telemetry_missing_or_stale',
            'degraded' => true,
        ]);

        $this->assertSame(
            'Decision-controller полива: разрешён деградированный полив (smart_soil_v1)',
            $message
        );
    }

    public function test_format_self_task_dispatch_retry_scheduled_contains_retry_progress(): void
    {
        $message = $this->formatter->format('SELF_TASK_DISPATCH_RETRY_SCHEDULED', [
            'task_type' => 'diagnostics',
            'enqueue_id' => 'enq-e43ee29f9e59409299df78f65e8f9b1e',
            'retry_count' => 2,
            'max_attempts' => 3,
            'next_retry_at' => '2026-02-17T07:59:06.869294',
        ]);

        $this->assertSame(
            'Scheduler запланировал повторную отправку для внутренней задачи диагностики (enqueue_id: enq-e43ee29f9e59409299df78f65e8f9b1e, попытка 2/3, следующая попытка: 2026-02-17T07:59:06.869294)',
            $message
        );
    }

    public function test_format_relay_autotune_completed_alias_is_supported(): void
    {
        $message = $this->formatter->format('RELAY_AUTOTUNE_COMPLETED', [
            'kp' => 6.7,
            'ki' => 0.11,
            'cycles_detected' => 3,
        ]);

        $this->assertSame('Автотюнинг завершён: Kp=6.700, Ki=0.1100 (3 циклов)', $message);
    }

    public function test_format_correction_skipped_water_level_contains_retry_context(): void
    {
        $message = $this->formatter->format('CORRECTION_SKIPPED_WATER_LEVEL', [
            'water_level_pct' => 12.0,
            'retry_after_sec' => 60,
        ]);

        $this->assertSame('Коррекция: мало воды (уровень 12.0%, повтор через 60 с)', $message);
    }

    public function test_format_correction_skipped_dose_discarded_contains_runtime_details(): void
    {
        $message = $this->formatter->format('CORRECTION_SKIPPED_DOSE_DISCARDED', [
            'reason' => 'below_min_dose_ms',
            'computed_duration_ms' => 10,
            'min_dose_ms' => 50,
            'dose_ml' => 0.1,
            'ml_per_sec' => 10.0,
        ]);

        $this->assertSame(
            'Коррекция: доза отброшена (below_min_dose_ms, 10мс < 50мс, доза 0.1000 мл, насос 10.0000 мл/с)',
            $message
        );
    }

    public function test_format_correction_skipped_freshness_contains_scope_and_retry(): void
    {
        $message = $this->formatter->format('CORRECTION_SKIPPED_FRESHNESS', [
            'sensor_scope' => 'observe_window',
            'sensor_type' => 'EC',
            'retry_after_sec' => 30,
        ]);

        $this->assertSame('Коррекция: устаревшие данные (observe window, EC, повтор через 30 с)', $message);
    }

    public function test_format_correction_skipped_window_not_ready_contains_reason_and_retry(): void
    {
        $message = $this->formatter->format('CORRECTION_SKIPPED_WINDOW_NOT_READY', [
            'sensor_scope' => 'decision_window',
            'reason' => 'Correction decision window not ready: PH=insufficient_samples,samples=2',
            'retry_after_sec' => 30,
        ]);

        $this->assertSame(
            'Коррекция: окно наблюдения не готово (decision window, Correction decision window not ready: PH=insufficient_samples,samples=2, повтор через 30 с)',
            $message
        );
    }

    public function test_format_correction_no_effect_contains_threshold_details(): void
    {
        $message = $this->formatter->format('CORRECTION_NO_EFFECT', [
            'pid_type' => 'ec',
            'actual_effect' => 0.02,
            'threshold_effect' => 0.1,
            'no_effect_limit' => 3,
        ]);

        $this->assertSame('Коррекция: нет наблюдаемого эффекта (EC, эффект 0.0200 < 0.1000, лимит 3)', $message);
    }

    public function test_format_command_timeout_contains_node_context_and_stale_online_hint(): void
    {
        $message = $this->formatter->format('COMMAND_TIMEOUT', [
            'cmd_id' => 'ae3-t1-z1-s1',
            'node_uid' => 'nd-test-irrig-1',
            'channel' => 'storage_state',
            'timeout_minutes' => 5,
            'node_status' => 'online',
            'node_last_seen_age_sec' => 182,
            'node_stale_online_candidate' => true,
        ]);

        $this->assertSame(
            'Таймаут команды (команда ae3-t1-z1-s1, нода nd-test-irrig-1, канал storage_state, таймаут 5 мин, статус узла online, last_seen 182 с назад, узел числится online, но heartbeat устарел)',
            $message
        );
    }

    public function test_format_ae_startup_probe_timeout_contains_probe_and_node_context(): void
    {
        $message = $this->formatter->format('AE_STARTUP_PROBE_TIMEOUT', [
            'probe_name' => 'irr_state_probe',
            'cmd_id' => 'ae3-t1-z1-s1',
            'node_uid' => 'nd-test-irrig-1',
            'channel' => 'storage_state',
            'node_status' => 'online',
            'node_last_seen_age_sec' => 182,
            'node_stale_online_candidate' => true,
        ]);

        $this->assertSame(
            'Стартовый probe ирригационного контура не ответил (probe irr_state_probe, команда ae3-t1-z1-s1, нода nd-test-irrig-1, канал storage_state, статус online, last_seen 182 с назад, online-статус выглядел устаревшим)',
            $message
        );
    }

    public function test_format_correction_observation_evaluated_contains_effect_metrics(): void
    {
        $message = $this->formatter->format('CORRECTION_OBSERVATION_EVALUATED', [
            'pid_type' => 'ph',
            'actual_effect' => 0.141,
            'expected_effect' => 1.176,
            'threshold_effect' => 0.294,
            'is_no_effect' => true,
            'no_effect_count_next' => 2,
        ]);

        $this->assertSame(
            'Коррекция: оценка отклика (PH, эффект 0.1410 / ожидалось 1.1760, порог 0.2940, no_effect=yes, счётчик 2)',
            $message
        );
    }

    public function test_format_ec_dosing_with_full_payload(): void
    {
        $message = $this->formatter->format('EC_DOSING', [
            'current_ec' => 1.2,
            'target_ec' => 1.5,
            'target_ec_min' => 1.4,
            'target_ec_max' => 1.6,
            'duration_ms' => 2500,
            'channel' => 'ec_npk_pump',
            'attempt' => 1,
        ]);

        $this->assertStringContainsString('EC', $message);
        $this->assertStringContainsString('1.20 мС/см', $message);
        $this->assertStringContainsString('1.40–1.60 мС/см', $message);
        $this->assertStringContainsString('2500 мс', $message);
        $this->assertStringContainsString('ec_npk_pump', $message);
    }

    public function test_format_ec_dosing_shows_target_range_over_single_target(): void
    {
        $message = $this->formatter->format('EC_DOSING', [
            'target_ec' => 1.5,
            'target_ec_min' => 1.4,
            'target_ec_max' => 1.6,
            'duration_ms' => 1000,
        ]);

        $this->assertStringContainsString('1.40–1.60 мС/см', $message);
        $this->assertStringNotContainsString('цель 1.50', $message);
    }

    public function test_format_ec_dosing_fallback_single_target(): void
    {
        $message = $this->formatter->format('EC_DOSING', [
            'target_ec' => 1.5,
            'duration_ms' => 800,
        ]);

        $this->assertStringContainsString('1.50 мС/см', $message);
    }

    public function test_format_ec_dosing_minimal_payload(): void
    {
        $message = $this->formatter->format('EC_DOSING', []);

        $this->assertStringContainsString('EC', $message);
    }

    public function test_format_ph_corrected_direction_up(): void
    {
        $message = $this->formatter->format('PH_CORRECTED', [
            'current_ph' => 5.8,
            'target_ph' => 6.2,
            'target_ph_min' => 6.0,
            'target_ph_max' => 6.5,
            'duration_ms' => 1200,
            'direction' => 'up',
            'channel' => 'ph_base_pump',
        ]);

        $this->assertStringContainsString('вверх', $message);
        $this->assertStringContainsString('5.80', $message);
        $this->assertStringContainsString('6.00–6.50', $message);
        $this->assertStringContainsString('1200 мс', $message);
        $this->assertStringContainsString('ph_base_pump', $message);
    }

    public function test_format_ph_corrected_direction_down(): void
    {
        $message = $this->formatter->format('PH_CORRECTED', [
            'current_ph' => 7.1,
            'target_ph' => 6.2,
            'duration_ms' => 900,
            'direction' => 'down',
        ]);

        $this->assertStringContainsString('вниз', $message);
        $this->assertStringContainsString('7.10', $message);
        $this->assertStringContainsString('6.20', $message);
    }

    public function test_format_ph_corrected_shows_attempt_when_greater_than_one(): void
    {
        $message = $this->formatter->format('PH_CORRECTED', [
            'direction' => 'up',
            'duration_ms' => 500,
            'attempt' => 3,
        ]);

        $this->assertStringContainsString('попытка 3', $message);
    }

    public function test_format_ph_corrected_hides_attempt_one(): void
    {
        $message = $this->formatter->format('PH_CORRECTED', [
            'direction' => 'up',
            'duration_ms' => 500,
            'attempt' => 1,
        ]);

        $this->assertStringNotContainsString('попытка', $message);
    }

    public function test_format_ph_corrected_minimal_payload(): void
    {
        $message = $this->formatter->format('PH_CORRECTED', []);

        $this->assertStringContainsString('pH', $message);
    }

    public function test_format_process_calibration_saved_includes_mode_window_and_gains(): void
    {
        $message = $this->formatter->format('PROCESS_CALIBRATION_SAVED', [
            'mode' => 'tank_recirc',
            'transport_delay_sec' => 20,
            'settle_sec' => 45,
            'confidence' => 0.91,
            'ec_gain_per_ml' => 0.11,
            'ph_up_gain_per_ml' => 0.08,
            'ph_down_gain_per_ml' => 0.07,
        ]);

        $this->assertStringContainsString('Process calibration обновлена (tank_recirc)', $message);
        $this->assertStringContainsString('окно 20+45 сек', $message);
        $this->assertStringContainsString('confidence 0.91', $message);
        $this->assertStringContainsString('EC=0.110', $message);
        $this->assertStringContainsString('pH+=0.080', $message);
        $this->assertStringContainsString('pH-=0.070', $message);
    }
}
