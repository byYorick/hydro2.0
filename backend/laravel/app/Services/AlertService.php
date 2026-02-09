<?php

namespace App\Services;

use App\Models\Alert;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class AlertService
{
    /**
     * Создать алерт.
     * При ошибке сохраняет в pending_alerts для последующей обработки через DLQ.
     */
    public function create(array $data): Alert
    {
        try {
            return DB::transaction(function () use ($data) {
                $alert = Alert::create($data);
                Log::info('Alert created', ['alert_id' => $alert->id, 'type' => $alert->type]);
                
                // Dispatch event для realtime обновлений после коммита транзакции
                // Это предотвращает отправку фантомных алертов при откате транзакции
                DB::afterCommit(function () use ($alert) {
                    $this->broadcastAlertCreated($alert);
                });
                
                return $alert;
            });
        } catch (\Exception $e) {
            // Сохраняем в pending_alerts для обработки через DLQ
            $this->saveToPendingAlerts($data, $e);
            throw $e;
        }
    }

    /**
     * Сохранить алерт в pending_alerts для последующей обработки.
     */
    private function saveToPendingAlerts(array $alertData, \Exception $e): void
    {
        try {
            DB::table('pending_alerts')->insert([
                'zone_id' => $alertData['zone_id'] ?? null,
                'source' => $alertData['source'] ?? 'biz',
                'code' => $alertData['code'] ?? null,
                'type' => $alertData['type'] ?? 'unknown',
                'details' => isset($alertData['details']) ? json_encode($alertData['details']) : null,
                'status' => 'pending',
                'attempts' => 0,
                'max_attempts' => 3,
                'last_error' => $e->getMessage(),
                'next_retry_at' => now(),
                'moved_to_dlq_at' => null,
                'created_at' => now(),
                'updated_at' => now(),
            ]);

            Log::warning('Alert saved to pending_alerts due to creation error', [
                'error' => $e->getMessage(),
                'alert_data' => $alertData,
            ]);
        } catch (\Exception $saveException) {
            // Если не удалось сохранить в pending_alerts - логируем критическую ошибку
            Log::error('Failed to save alert to pending_alerts', [
                'original_error' => $e->getMessage(),
                'save_error' => $saveException->getMessage(),
                'alert_data' => $alertData,
            ]);
        }
    }

    /**
     * Проверить, должен ли алерт быть заблокирован rate limiting.
     * 
     * @param string $errorCode Код ошибки
     * @param int|null $zoneId ID зоны
     * @return bool true если алерт должен быть заблокирован
     */
    private function shouldRateLimit(string $errorCode, ?int $zoneId): bool
    {
        // Если rate limiting отключен - не блокируем
        if (!config('alerts.rate_limiting.enabled', true)) {
            return false;
        }

        // Критичные ошибки не подлежат rate limiting
        $criticalCodes = config('alerts.rate_limiting.critical_codes', []);
        if (in_array($errorCode, $criticalCodes)) {
            return false;
        }

        // Проверяем количество алертов за последнюю минуту для этой зоны
        $maxPerMinute = config('alerts.rate_limiting.max_per_minute', 10);
        $count = Alert::where('zone_id', $zoneId)
            ->where('created_at', '>', now()->subMinute())
            ->count();

        if ($count >= $maxPerMinute) {
            Log::warning('Alert rate limit exceeded', [
                'code' => $errorCode,
                'zone_id' => $zoneId,
                'count' => $count,
                'max_per_minute' => $maxPerMinute,
            ]);
            return true;
        }

        return false;
    }

    /**
     * Создать или обновить активный алерт с дедупликацией.
     * 
     * Ключ дедупликации: (zone_id, code, status='ACTIVE')
     * 
     * Логика:
     * - Если активный алерт с таким (zone_id, code) уже существует:
     *   - Увеличивает details.count на 1
     *   - Обновляет details.last_seen_at на текущее время
     *   - Объединяет новые details с существующими
     *   - Отправляет AlertUpdated event
     * - Если алерт не найден:
     *   - Создает новый алерт с details.count=1 и details.last_seen_at=текущее время
     *   - Отправляет AlertCreated event
     * 
     * @param array $data Данные алерта: zone_id, source, code, type, details, severity, node_uid, hardware_id, ts_device
     * @return array ['alert' => Alert, 'created' => bool, 'event_id' => int|null]
     */
    public function createOrUpdateActive(array $data): array
    {
        return DB::transaction(function () use ($data) {
            $zoneId = $data['zone_id'] ?? null;
            $code = $data['code'] ?? null;
            
            if (!$code) {
                throw new \InvalidArgumentException('code is required for deduplication');
            }
            
            // Ищем существующий активный алерт по ключу дедупликации
            // Используем lockForUpdate() для предотвращения race conditions
            $existing = Alert::where('zone_id', $zoneId)
                ->where('code', $code)
                ->where('status', 'ACTIVE')
                ->lockForUpdate()
                ->first();
            
            // Проверка rate limiting (только если алерт не существует - для новых алертов)
            if (!$existing && $this->shouldRateLimit($code, $zoneId)) {
                // Rate limit достигнут для нового алерта - логируем и пропускаем создание
                Log::warning('Alert creation rate limited', [
                    'code' => $code,
                    'zone_id' => $zoneId,
                ]);
                
                // Возвращаем null-результат вместо исключения для более мягкой обработки
                return [
                    'alert' => null,
                    'created' => false,
                    'event_id' => null,
                    'rate_limited' => true,
                ];
            }
            
            $now = now();
            $nowIso = $now->toIso8601String();
            
            if ($existing) {
                // Атомарно увеличиваем счетчик ошибок в БД
                DB::table('alerts')
                    ->where('id', $existing->id)
                    ->increment('error_count');
                
                // Получаем обновленное значение error_count
                $existing->refresh();
                $currentCount = $existing->error_count ?? 1;
                
                // Обновляем details
                $existingDetails = $existing->details ?? [];
                $existingDetails['count'] = $currentCount; // Синхронизируем с error_count
                $existingDetails['last_seen_at'] = $nowIso;
                
                // Объединяем новые details с существующими
                if (isset($data['details']) && is_array($data['details'])) {
                    $existingDetails = array_merge($existingDetails, $data['details']);
                }
                
                // Обновляем severity, если указан
                if (isset($data['severity'])) {
                    $existingDetails['severity'] = $data['severity'];
                }
                
                // Обновляем node_uid/hardware_id, если указаны
                if (isset($data['node_uid'])) {
                    $existingDetails['node_uid'] = $data['node_uid'];
                }
                if (isset($data['hardware_id'])) {
                    $existingDetails['hardware_id'] = $data['hardware_id'];
                }
                
                // Обновляем ts_device, если указан
                if (isset($data['ts_device'])) {
                    $existingDetails['ts_device'] = $data['ts_device'];
                }
                
                $existing->update([
                    'details' => $existingDetails,
                ]);
                
                Log::info('Alert updated', [
                    'alert_id' => $existing->id,
                    'code' => $code,
                    'error_count' => $currentCount,
                    'count' => $existingDetails['count'],
                ]);
                
                // Создаем событие в zone_events
                $eventId = null;
                if ($zoneId) {
                    $eventId = DB::table('zone_events')->insertGetId([
                        'zone_id' => $zoneId,
                        'type' => 'ALERT_UPDATED',
                        'payload_json' => json_encode([  // Используем payload_json вместо details
                            'alert_id' => $existing->id,
                            'code' => $code,
                            'error_count' => $currentCount,
                            'count' => $existingDetails['count'],
                            'updated_at' => $nowIso,
                        ]),
                        'created_at' => $now,
                    ]);
                }
                
                // Dispatch event для realtime обновлений после коммита транзакции
                DB::afterCommit(function () use ($existing) {
                    $this->broadcastAlertUpdated($existing);
                });
                
                return [
                    'alert' => $existing->fresh(),
                    'created' => false,
                    'event_id' => $eventId,
                ];
            } else {
                // Создаем новый алерт
                $newDetails = $data['details'] ?? [];
                $newDetails['count'] = 1; // Синхронизируем с error_count
                $newDetails['last_seen_at'] = $nowIso;
                
                // Добавляем severity, если указан
                if (isset($data['severity'])) {
                    $newDetails['severity'] = $data['severity'];
                }
                
                // Добавляем node_uid/hardware_id, если указаны
                if (isset($data['node_uid'])) {
                    $newDetails['node_uid'] = $data['node_uid'];
                }
                if (isset($data['hardware_id'])) {
                    $newDetails['hardware_id'] = $data['hardware_id'];
                }
                
                // Добавляем ts_device, если указан
                if (isset($data['ts_device'])) {
                    $newDetails['ts_device'] = $data['ts_device'];
                }
                
                $alert = Alert::create([
                    'zone_id' => $zoneId,
                    'source' => $data['source'] ?? 'biz',
                    'code' => $code,
                    'type' => $data['type'] ?? 'unknown',
                    'status' => 'ACTIVE',
                    'error_count' => 1, // Начальное значение счетчика
                    'details' => $newDetails,
                    'created_at' => $now,
                ]);
                
                Log::info('Alert created', [
                    'alert_id' => $alert->id,
                    'code' => $code,
                    'zone_id' => $zoneId,
                ]);
                
                // Создаем событие в zone_events
                $eventId = null;
                if ($zoneId) {
                    $eventId = DB::table('zone_events')->insertGetId([
                        'zone_id' => $zoneId,
                        'type' => 'ALERT_CREATED',
                        'payload_json' => json_encode([  // Используем payload_json вместо details
                            'alert_id' => $alert->id,
                            'code' => $code,
                            'type' => $alert->type,
                            'source' => $alert->source,
                        ]),
                        'created_at' => $now,
                    ]);
                }
                
                // Dispatch event для realtime обновлений после коммита транзакции
                DB::afterCommit(function () use ($alert) {
                    $this->broadcastAlertCreated($alert);
                });
                
                return [
                    'alert' => $alert,
                    'created' => true,
                    'event_id' => $eventId,
                ];
            }
        });
    }

    /**
     * Закрыть активный алерт по ключу (zone_id, code).
     *
     * @param int|null $zoneId ID зоны (null для unassigned alert)
     * @param string $code Код алерта
     * @param array $context Дополнительный контекст (например, details)
     * @return array ['resolved' => bool, 'alert' => Alert|null, 'event_id' => int|null]
     */
    public function resolveByCode(?int $zoneId, string $code, array $context = []): array
    {
        return DB::transaction(function () use ($zoneId, $code, $context) {
            $query = Alert::where('code', $code)
                ->where('status', 'ACTIVE');

            if ($zoneId === null) {
                $query->whereNull('zone_id');
            } else {
                $query->where('zone_id', $zoneId);
            }

            $alert = $query->lockForUpdate()->first();
            if (! $alert) {
                return [
                    'resolved' => false,
                    'alert' => null,
                    'event_id' => null,
                ];
            }

            $now = now();
            $details = is_array($alert->details) ? $alert->details : [];
            if (isset($context['details']) && is_array($context['details'])) {
                $details = array_merge($details, $context['details']);
            }
            $details['resolved_at'] = $now->toIso8601String();

            $alert->update([
                'status' => 'RESOLVED',
                'resolved_at' => $now,
                'details' => $details,
            ]);

            $eventId = null;
            if ($alert->zone_id) {
                $eventId = DB::table('zone_events')->insertGetId([
                    'zone_id' => $alert->zone_id,
                    'type' => 'ALERT_RESOLVED',
                    'payload_json' => json_encode([
                        'alert_id' => $alert->id,
                        'code' => $alert->code,
                        'resolved_at' => $now->toIso8601String(),
                    ]),
                    'created_at' => $now,
                ]);
            }

            DB::afterCommit(function () use ($alert) {
                $this->broadcastAlertUpdated($alert->fresh());
            });

            Log::info('Alert resolved by code', [
                'alert_id' => $alert->id,
                'zone_id' => $zoneId,
                'code' => $code,
            ]);

            return [
                'resolved' => true,
                'alert' => $alert->fresh(),
                'event_id' => $eventId,
            ];
        });
    }

    /**
     * Подтвердить/принять алерт
     */
    public function acknowledge(Alert $alert): Alert
    {
        return DB::transaction(function () use ($alert) {
            if ($alert->status === 'resolved' || $alert->status === 'RESOLVED') {
                throw new \DomainException('Alert is already resolved');
            }

            $alert->update([
                'status' => 'RESOLVED',
                'resolved_at' => now(),
            ]);

            // Создаем событие ALERT_RESOLVED
            if ($alert->zone_id) {
                DB::table('zone_events')->insert([
                    'zone_id' => $alert->zone_id,
                    'type' => 'ALERT_RESOLVED',
                    'payload_json' => json_encode([  // Используем payload_json вместо details
                        'alert_id' => $alert->id,
                        'alert_type' => $alert->type,
                        'resolved_at' => $alert->resolved_at->toIso8601String(),
                    ]),
                    'created_at' => now(),
                ]);
            }

            Log::info('Alert acknowledged', ['alert_id' => $alert->id]);
            return $alert->fresh();
        });
    }

    /**
     * Отправить AlertCreated event через WebSocket
     */
    private function broadcastAlertCreated(Alert $alert): void
    {
        $alertData = [
            'id' => $alert->id,
            'type' => $alert->type,
            'source' => $alert->source,
            'code' => $alert->code,
            'status' => $alert->status,
            'zone_id' => $alert->zone_id,
            'details' => $alert->details,
            'created_at' => $alert->created_at?->toIso8601String(),
        ];
        
        // Event автоматически отправляется в нужные каналы (hydro.alerts и hydro.zones.{id})
        event(new \App\Events\AlertCreated($alertData));
    }

    /**
     * Отправить AlertUpdated event через WebSocket
     */
    private function broadcastAlertUpdated(Alert $alert): void
    {
        $alertData = [
            'id' => $alert->id,
            'type' => $alert->type,
            'source' => $alert->source,
            'code' => $alert->code,
            'status' => $alert->status,
            'zone_id' => $alert->zone_id,
            'details' => $alert->details,
            'created_at' => $alert->created_at?->toIso8601String(),
        ];
        
        // Event автоматически отправляется в нужные каналы (hydro.alerts и hydro.zones.{id})
        event(new \App\Events\AlertUpdated($alertData));
    }
}
