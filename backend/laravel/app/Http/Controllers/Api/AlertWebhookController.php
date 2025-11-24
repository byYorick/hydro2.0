<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Services\AlertService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class AlertWebhookController extends Controller
{
    public function __construct(
        private AlertService $alertService
    ) {}

    /**
     * Принимает webhook от Alertmanager
     * Формат: https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
     */
    public function webhook(Request $request)
    {
        // Валидация webhook данных от Alertmanager
        // Формат: https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
        // Поле alerts может быть пустым массивом или отсутствовать (для совместимости)
        
        // Базовые правила валидации
        $rules = [
            'version' => ['nullable', 'string'],
            'groupKey' => ['nullable', 'string'],
            'status' => ['nullable', 'string', 'in:firing,resolved'],
            'receiver' => ['nullable', 'string'],
            'alerts' => ['nullable', 'array'],
        ];
        
        // Добавляем вложенные правила для alerts только если alerts присутствует и не пустое
        if ($request->has('alerts') && !empty($request->input('alerts'))) {
            $rules['alerts.*.status'] = ['required', 'string', 'in:firing,resolved'];
            $rules['alerts.*.labels'] = ['required', 'array'];
            $rules['alerts.*.annotations'] = ['nullable', 'array'];
            $rules['alerts.*.startsAt'] = ['nullable', 'date'];
            $rules['alerts.*.endsAt'] = ['nullable', 'date'];
        }
        
        $data = $request->validate($rules);
        
        Log::info('Alertmanager webhook received', ['data' => $data]);

        // Alertmanager отправляет массив алертов
        // Обрабатываем только если массив не пустой
        if (!empty($data['alerts']) && is_array($data['alerts'])) {
            foreach ($data['alerts'] as $alertData) {
                $this->processAlert($alertData);
            }
        }

        return response()->json(['status' => 'ok'], 200);
    }

    private function processAlert(array $alertData): void
    {
        $status = $alertData['status'] ?? 'unknown'; // 'firing' или 'resolved'
        $labels = $alertData['labels'] ?? [];
        $annotations = $alertData['annotations'] ?? [];

        $alertName = $labels['alertname'] ?? 'Unknown';
        $severity = $labels['severity'] ?? 'warning';

        // Определяем zone_id из labels, если есть
        $zoneId = null;
        if (isset($labels['zone_id'])) {
            $zoneId = (int) $labels['zone_id'];
        }

        // Если алерт resolved, обновляем существующий
        if ($status === 'resolved') {
            // Ищем активный алерт с таким типом
            $alert = \App\Models\Alert::where('type', $alertName)
                ->where('status', 'ACTIVE')
                ->when($zoneId, fn($q) => $q->where('zone_id', $zoneId))
                ->first();

            if ($alert) {
                $this->alertService->acknowledge($alert);
            }
            return;
        }

        // Если алерт firing, создаем новый
        if ($status === 'firing') {
            $this->alertService->create([
                'zone_id' => $zoneId,
                'type' => $alertName,
                'status' => 'ACTIVE',
                'details' => [
                    'severity' => $severity,
                    'labels' => $labels,
                    'annotations' => $annotations,
                    'startsAt' => $alertData['startsAt'] ?? now()->toIso8601String(),
                ],
            ]);
        }
    }
}
