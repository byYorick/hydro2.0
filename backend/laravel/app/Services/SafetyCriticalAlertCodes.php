<?php

namespace App\Services;

/**
 * Коды алертов, которые держат safety-блокировку, пока status = ACTIVE.
 *
 * AE3 (`PgZoneAlertRepository`) и pump-safety (`get_active_critical_alerts`)
 * считают блокирующими только строки со status = 'ACTIVE'. Подтверждение
 * записывает acknowledged_at / acknowledged_by и не меняет статус.
 * Ручное закрытие этих кодов запрещено, пока условие не снято автоматическим resolve.
 *
 * Единственный список. UI-группировка дублирует его в SAFETY_CRITICAL_CODES.
 */
final class SafetyCriticalAlertCodes
{
    /**
     * @var list<string>
     */
    public const CODES = [
        // Сухой ход и interlock насоса: common.pump_safety читает только ACTIVE.
        'biz_dry_run',
        'biz_no_flow',
        'biz_overcurrent',
        'biz_pump_stuck_on',
        'biz_flow_stop_failed_hardware_may_be_active',
        // Узел offline (history-logger biz_node_offline).
        'biz_node_offline',
        // Перегрев раствора.
        'biz_solution_temp_high',
        'solution_temp_out_of_band',
        // E-STOP: событие прошивки и код, которым уже поднимается алерт.
        'emergency_stop_activated',
        'biz_irrigation_estop',
    ];

    public function contains(?string $code): bool
    {
        $normalized = strtolower(trim((string) $code));

        return $normalized !== '' && in_array($normalized, self::CODES, true);
    }
}
