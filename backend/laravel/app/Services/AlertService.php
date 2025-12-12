<?php

namespace App\Services;

use App\Models\Alert;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class AlertService
{
    /**
     * Создать алерт
     */
    public function create(array $data): Alert
    {
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
            $existing = Alert::where('zone_id', $zoneId)
                ->where('code', $code)
                ->where('status', 'ACTIVE')
                ->first();
            
            $now = now();
            $nowIso = $now->toIso8601String();
            
            if ($existing) {
                // Обновляем существующий алерт
                $existingDetails = $existing->details ?? [];
                
                // Увеличиваем счетчик
                $currentCount = $existingDetails['count'] ?? 0;
                $existingDetails['count'] = $currentCount + 1;
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
                    'count' => $existingDetails['count'],
                ]);
                
                // Создаем событие в zone_events
                $eventId = null;
                if ($zoneId) {
                    $eventId = DB::table('zone_events')->insertGetId([
                        'zone_id' => $zoneId,
                        'type' => 'ALERT_UPDATED',
                        'details' => json_encode([
                            'alert_id' => $existing->id,
                            'code' => $code,
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
                $newDetails['count'] = 1;
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
                        'details' => json_encode([
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
                    'details' => json_encode([
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

