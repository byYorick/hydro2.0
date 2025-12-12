<?php

namespace App\Services;

use App\Models\Command;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Http;

class PipelineMetricsService
{
    /**
     * Записывает метрики latency команды.
     * 
     * Отправляет метрики в history-logger для экспорта в Prometheus.
     */
    public function recordCommandLatency(Command $command): void
    {
        try {
            // Вычисляем latency только если есть все необходимые timestamps
            if (!$command->sent_at) {
                return;
            }
            
            $sentAt = $command->sent_at;
            $acceptedAt = $command->ack_at; // ack_at используется для ACCEPTED
            $doneAt = null;
            
            // Определяем done_at в зависимости от статуса
            if ($command->status === Command::STATUS_DONE) {
                $doneAt = $command->ack_at ?? now(); // Если DONE, используем ack_at или текущее время
            } elseif (in_array($command->status, [Command::STATUS_FAILED, Command::STATUS_TIMEOUT])) {
                $doneAt = $command->failed_at ?? now();
            }
            
            // Отправляем метрики в history-logger
            $historyLoggerUrl = config('services.history_logger.url', 'http://history-logger:9300');
            
            $metrics = [];
            
            if ($acceptedAt) {
                $sentToAccepted = $sentAt->diffInSeconds($acceptedAt);
                $metrics['sent_to_accepted_seconds'] = $sentToAccepted;
            }
            
            if ($doneAt) {
                if ($acceptedAt) {
                    $acceptedToDone = $acceptedAt->diffInSeconds($doneAt);
                    $metrics['accepted_to_done_seconds'] = $acceptedToDone;
                }
                
                $e2eLatency = $sentAt->diffInSeconds($doneAt);
                $metrics['e2e_latency_seconds'] = $e2eLatency;
            }
            
            if (!empty($metrics)) {
                Http::timeout(1)->post("{$historyLoggerUrl}/internal/metrics/command-latency", [
                    'cmd_id' => $command->cmd_id,
                    'metrics' => $metrics,
                ]);
            }
        } catch (\Exception $e) {
            // Не логируем ошибки метрик, чтобы не засорять логи
            Log::debug('Failed to record command latency metrics', [
                'cmd_id' => $command->cmd_id,
                'error' => $e->getMessage(),
            ]);
        }
    }
    
    /**
     * Записывает метрики latency доставки ошибки.
     */
    public function recordErrorDeliveryLatency(
        \DateTime $mqttReceivedAt,
        ?\DateTime $laravelReceivedAt = null,
        ?\DateTime $wsSentAt = null
    ): void {
        try {
            $historyLoggerUrl = config('services.history_logger.url', 'http://history-logger:9300');
            
            $metrics = [];
            
            if ($laravelReceivedAt) {
                $mqttToLaravel = $mqttReceivedAt->diffInSeconds($laravelReceivedAt);
                $metrics['mqtt_to_laravel_seconds'] = $mqttToLaravel;
            }
            
            if ($wsSentAt) {
                if ($laravelReceivedAt) {
                    $laravelToWs = $laravelReceivedAt->diffInSeconds($wsSentAt);
                    $metrics['laravel_to_ws_seconds'] = $laravelToWs;
                }
                
                $totalLatency = $mqttReceivedAt->diffInSeconds($wsSentAt);
                $metrics['total_latency_seconds'] = $totalLatency;
            }
            
            if (!empty($metrics)) {
                Http::timeout(1)->post("{$historyLoggerUrl}/internal/metrics/error-delivery-latency", [
                    'metrics' => $metrics,
                ]);
            }
        } catch (\Exception $e) {
            Log::debug('Failed to record error delivery latency metrics', [
                'error' => $e->getMessage(),
            ]);
        }
    }
}
