<?php

namespace App\Services\LaunchFlow;

use App\Models\Zone;
use App\Services\ZoneReadinessService;

/**
 * Обогащает readiness-ошибки структурой { code, message, action } для frontend launcher'а.
 */
class LaunchFlowReadinessEnricher
{
    public function __construct(private readonly ZoneReadinessService $readiness)
    {
    }

    /**
     * @return array{ready: bool, blockers: list<array{code: string, message: string, severity: string, action?: array<string, mixed>}>, warnings: list<string>}
     */
    public function forZone(Zone $zone): array
    {
        $raw = $this->readiness->validate($zone->id);
        $ready = (bool) ($raw['ready'] ?? false);
        $warnings = array_values($raw['warnings'] ?? []);
        $details = is_array($raw['details'] ?? null) ? $raw['details'] : [];
        $errorDetails = is_array($details['error_details'] ?? null) ? $details['error_details'] : [];
        $checks = is_array($details['checks'] ?? null) ? $details['checks'] : [];

        $blockers = [];

        if (($checks['has_nodes'] ?? true) === false) {
            $blockers[] = [
                'code' => 'no_nodes_bound',
                'message' => 'В зоне нет привязанных узлов',
                'severity' => 'error',
                'action' => [
                    'type' => 'open_nodes_binding',
                    'route' => ['name' => 'zones.infrastructure', 'params' => ['zone' => $zone->id]],
                    'label' => 'Привязать узлы',
                ],
            ];
        }

        if (($checks['online_nodes'] ?? true) === false) {
            $blockers[] = [
                'code' => 'nodes_offline',
                'message' => 'Нет онлайн-узлов в зоне',
                'severity' => 'error',
                'action' => [
                    'type' => 'diagnostics',
                    'route' => ['name' => 'zones.show', 'params' => ['zone' => $zone->id]],
                    'label' => 'Проверить состояние узлов',
                ],
            ];
        }

        foreach ($errorDetails as $issue) {
            if (! is_array($issue)) {
                continue;
            }
            $blockers = array_merge($blockers, $this->translateIssue($zone, $issue));
        }

        return [
            'ready' => $ready,
            'blockers' => $blockers,
            'warnings' => array_values(array_filter($warnings, 'is_string')),
        ];
    }

    /**
     * @param array<string, mixed> $issue
     * @return list<array<string, mixed>>
     */
    private function translateIssue(Zone $zone, array $issue): array
    {
        $type = (string) ($issue['type'] ?? '');
        $out = [];

        switch ($type) {
            case 'missing_bindings':
                foreach ($issue['bindings'] ?? [] as $role) {
                    if (! is_string($role) || $role === '') {
                        continue;
                    }
                    $out[] = [
                        'code' => 'missing_binding:'.$role,
                        'message' => $this->bindingMessage($role),
                        'severity' => 'error',
                        'action' => [
                            'type' => 'open_binding_editor',
                            'role' => $role,
                            'route' => ['name' => 'zones.infrastructure', 'params' => ['zone' => $zone->id]],
                            'label' => 'Привязать канал',
                        ],
                    ];
                }
                break;
            case 'missing_calibrations':
                foreach ($issue['bindings'] ?? [] as $role) {
                    if (! is_string($role) || $role === '') {
                        continue;
                    }
                    $out[] = [
                        'code' => 'missing_calibration:'.$role,
                        'message' => $this->calibrationMessage($role),
                        'severity' => 'error',
                        'action' => [
                            'type' => 'open_calibration',
                            'role' => $role,
                            'route' => ['name' => 'zones.calibration', 'params' => ['zone' => $zone->id, 'pump' => $role]],
                            'label' => 'Выполнить калибровку',
                        ],
                    ];
                }
                break;
            case 'missing_pid_configs':
                foreach ($issue['pid_types'] ?? [] as $pidType) {
                    if (! is_string($pidType) || $pidType === '') {
                        continue;
                    }
                    $out[] = [
                        'code' => 'missing_pid_config:'.$pidType,
                        'message' => 'Не сохранён PID-конфиг для '.strtoupper($pidType),
                        'severity' => 'error',
                        'action' => [
                            'type' => 'open_pid_editor',
                            'pid_type' => $pidType,
                            'route' => ['name' => 'zones.edit', 'params' => ['zone' => $zone->id]],
                            'label' => 'Настроить PID',
                        ],
                    ];
                }
                break;
            case 'missing_process_calibrations':
                foreach ($issue['modes'] ?? [] as $mode) {
                    if (! is_string($mode) || $mode === '') {
                        continue;
                    }
                    $out[] = [
                        'code' => 'missing_process_calibration:'.$mode,
                        'message' => 'Не сохранена process-калибровка '.$mode,
                        'severity' => 'error',
                        'action' => [
                            'type' => 'open_process_calibration',
                            'mode' => $mode,
                            'route' => ['name' => 'zones.calibration', 'params' => ['zone' => $zone->id, 'mode' => $mode]],
                            'label' => 'Выполнить калибровку',
                        ],
                    ];
                }
                break;
            case 'blocking_alerts':
                foreach ($issue['alerts'] ?? [] as $alert) {
                    if (! is_array($alert)) {
                        continue;
                    }
                    $code = (string) ($alert['code'] ?? 'blocking_alert');
                    $out[] = [
                        'code' => $code,
                        'message' => (string) ($alert['message'] ?? 'Заблокировано alert-ом'),
                        'severity' => 'error',
                        'action' => [
                            'type' => 'open_alerts',
                            'route' => ['name' => 'alerts.index', 'params' => []],
                            'label' => 'Открыть алерты',
                        ],
                    ];
                }
                break;
            case 'dispatch_disabled':
                $out[] = [
                    'code' => 'dispatch_disabled',
                    'message' => 'Запуск отключён runtime-флагом автоматики',
                    'severity' => 'error',
                ];
                break;
            default:
                $out[] = [
                    'code' => $type !== '' ? $type : 'unknown',
                    'message' => (string) ($issue['message'] ?? 'Неизвестная проблема готовности'),
                    'severity' => 'error',
                ];
                break;
        }

        return $out;
    }

    private function bindingMessage(string $role): string
    {
        return match ($role) {
            'pump_main' => 'Основная помпа не привязана',
            'drain' => 'Дренаж не привязан',
            'pump_acid' => 'Насос pH (кислота) не привязан',
            'pump_base' => 'Насос pH (щёлочь) не привязан',
            'pump_a' => 'Насос EC A (NPK) не привязан',
            'pump_b' => 'Насос EC B (Ca) не привязан',
            'pump_c' => 'Насос EC C (Mg) не привязан',
            'pump_d' => 'Насос EC D (Micro) не привязан',
            default => 'Не привязан канал: '.$role,
        };
    }

    private function calibrationMessage(string $role): string
    {
        return match ($role) {
            'pump_acid', 'pump_base' => 'Требуется калибровка pH-насоса ('.$role.')',
            'pump_a', 'pump_b', 'pump_c', 'pump_d' => 'Требуется калибровка EC-насоса ('.$role.')',
            default => 'Требуется калибровка насоса: '.$role,
        };
    }
}
