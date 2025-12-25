<?php

namespace App\Services;

use App\Models\Zone;
use App\Models\GrowCycle;
use App\Enums\GrowCycleStatus;
use App\Events\ZoneUpdated;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Str;

class ZoneService
{
    /**
     * Создать зону
     */
    public function create(array $data): Zone
    {
        return DB::transaction(function () use ($data) {
            // Генерируем UID, если не указан
            if (empty($data['uid'])) {
                $data['uid'] = $this->generateZoneUid($data['name'] ?? 'untitled');
            }
            
            $zone = Zone::create($data);
            Log::info('Zone created', ['zone_id' => $zone->id, 'uid' => $zone->uid, 'name' => $zone->name]);
            
            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));
            
            return $zone;
        });
    }

    /**
     * Генерирует UID для зоны на основе названия
     * 
     * @param string $name Название зоны (может быть на русском)
     * @return string Сгенерированный UID в формате zn-{transliterated-name}
     */
    private function generateZoneUid(string $name): string
    {
        $prefix = 'zn-';
        
        if (empty($name) || trim($name) === '') {
            return $prefix . 'untitled-' . strtolower(Str::random(6));
        }

        // Используем Str::slug для транслитерации и нормализации
        // Str::slug автоматически транслитерирует русские буквы
        $transliterated = Str::slug(trim($name), '-');
        
        // Если после обработки ничего не осталось, используем значение по умолчанию
        if (empty($transliterated)) {
            $transliterated = 'untitled-' . strtolower(Str::random(6));
        }

        // Ограничиваем длину (оставляем место для префикса и суффикса)
        $maxLength = 50 - strlen($prefix);
        if (strlen($transliterated) > $maxLength) {
            $transliterated = substr($transliterated, 0, $maxLength);
            // Убираем возможный дефис в конце после обрезки
            $transliterated = rtrim($transliterated, '-');
        }

        $uid = $prefix . $transliterated;
        
        // Проверяем уникальность UID и добавляем суффикс, если нужно
        $counter = 0;
        $originalUid = $uid;
        while (Zone::where('uid', $uid)->exists()) {
            $counter++;
            $suffix = '-' . $counter;
            $maxLengthWithSuffix = $maxLength - strlen($suffix);
            $base = substr($transliterated, 0, $maxLengthWithSuffix);
            $uid = $prefix . rtrim($base, '-') . $suffix;
            
            // Защита от бесконечного цикла
            if ($counter > 1000) {
                $uid = $originalUid . '-' . time();
                break;
            }
        }

        return $uid;
    }

    /**
     * Обновить зону
     */
    public function update(Zone $zone, array $data): Zone
    {
        return DB::transaction(function () use ($zone, $data) {
            $zone->update($data);
            Log::info('Zone updated', ['zone_id' => $zone->id]);
            $zone = $zone->fresh();
            
            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));
            
            return $zone;
        });
    }

    /**
     * Удалить зону (с проверкой инвариантов)
     */
    public function delete(Zone $zone): void
    {
        DB::transaction(function () use ($zone) {
            // Проверка: нельзя удалить зону с активным циклом
            if ($zone->activeGrowCycle) {
                throw new \DomainException('Cannot delete zone with active grow cycle. Please finish or abort cycle first.');
            }

            // Проверка: нельзя удалить зону с привязанными узлами
            if ($zone->nodes()->count() > 0) {
                throw new \DomainException('Cannot delete zone with attached nodes. Please detach nodes first.');
            }

            $zoneId = $zone->id;
            $zoneName = $zone->name;
            $zone->delete();
            Log::info('Zone deleted', ['zone_id' => $zoneId, 'name' => $zoneName]);
        });
    }

    /**
     * Назначить рецепт на зону
     * 
     * @deprecated Используйте GrowCycleService::createCycle() вместо этого метода
     * Этот метод оставлен для обратной совместимости, но создает только ZoneRecipeInstance без GrowCycle
     */
    public function attachRecipe(Zone $zone, int $recipeId, ?\DateTimeInterface $startAt = null)
    {
        Log::warning('ZoneService::attachRecipe() is deprecated. Use GrowCycleService::createCycle() instead.', [
            'zone_id' => $zone->id,
            'recipe_id' => $recipeId,
        ]);

        throw new \DomainException('ZoneService::attachRecipe() is deprecated. Please use GrowCycleService::createCycle() to create a new grow cycle with a recipe revision.');
    }

    /**
     * Изменить фазу рецепта зоны
     * 
     * @deprecated Используйте GrowCycleService::setPhase() или GrowCycleService::advancePhase() вместо этого метода
     */
    public function changePhase(Zone $zone, int $phaseIndex)
    {
        Log::warning('ZoneService::changePhase() is deprecated. Use GrowCycleService::setPhase() or GrowCycleService::advancePhase() instead.', [
            'zone_id' => $zone->id,
            'phase_index' => $phaseIndex,
        ]);

        throw new \DomainException('ZoneService::changePhase() is deprecated. Please use GrowCycleService::setPhase() or GrowCycleService::advancePhase() to change phases in a grow cycle.');
    }

    /**
     * Перейти на следующую фазу рецепта
     * 
     * @deprecated Используйте GrowCycleService::advancePhase() вместо этого метода
     */
    public function nextPhase(Zone $zone)
    {
        Log::warning('ZoneService::nextPhase() is deprecated. Use GrowCycleService::advancePhase() instead.', [
            'zone_id' => $zone->id,
        ]);

        throw new \DomainException('ZoneService::nextPhase() is deprecated. Please use GrowCycleService::advancePhase() to advance to the next phase in a grow cycle.');
    }

    /**
     * Пауза/возобновление зоны
     */
    public function pause(Zone $zone): Zone
    {
        if ($zone->status === 'PAUSED') {
            throw new \DomainException('Zone is already paused');
        }

        return DB::transaction(function () use ($zone) {
            try {
                $oldStatus = $zone->status;
                $zone->update(['status' => 'PAUSED']);
                
                // Создаем zone_event
                $hasPayloadJson = Schema::hasColumn('zone_events', 'payload_json');
                
                $eventPayload = json_encode([
                    'zone_id' => $zone->id,
                    'from_status' => $oldStatus ?? null,
                    'to_status' => 'PAUSED',
                    'paused_at' => now()->toIso8601String(),
                ]);
                
                $eventData = [
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_PAUSED',
                    'created_at' => now(),
                ];
                
                if ($hasPayloadJson) {
                    $eventData['payload_json'] = $eventPayload;
                } else {
                    $eventData['details'] = $eventPayload;
                }
                
                DB::table('zone_events')->insert($eventData);

                Log::info('Zone paused', ['zone_id' => $zone->id]);
                $zone = $zone->fresh();
                
                // Dispatch event для уведомления Python-сервиса
                try {
                    event(new ZoneUpdated($zone));
                } catch (\Exception $e) {
                    // Игнорируем ошибки при dispatch event, это не критично
                    Log::warning('Failed to dispatch ZoneUpdated event', [
                        'zone_id' => $zone->id,
                        'error' => $e->getMessage()
                    ]);
                }
                
                return $zone;
            } catch (\Exception $e) {
                Log::error('Error in ZoneService::pause', [
                    'zone_id' => $zone->id,
                    'error' => $e->getMessage(),
                    'trace' => $e->getTraceAsString()
                ]);
                throw $e;
            }
        });
    }

    /**
     * Возобновление зоны
     */
    public function resume(Zone $zone): Zone
    {
        if ($zone->status !== 'PAUSED') {
            throw new \DomainException('Zone is not paused');
        }

        return DB::transaction(function () use ($zone) {
            $zone->update(['status' => 'RUNNING']);
            
            // Создаем zone_event
            $hasPayloadJson = Schema::hasColumn('zone_events', 'payload_json');
            
            $eventPayload = json_encode([
                'zone_id' => $zone->id,
                'from_status' => 'PAUSED',
                'to_status' => 'RUNNING',
                'resumed_at' => now()->toIso8601String(),
            ]);
            
            $eventData = [
                'zone_id' => $zone->id,
                'type' => 'CYCLE_RESUMED',
                'created_at' => now(),
            ];
            
            if ($hasPayloadJson) {
                $eventData['payload_json'] = $eventPayload;
            } else {
                $eventData['details'] = $eventPayload;
            }
            
            DB::table('zone_events')->insert($eventData);

            Log::info('Zone resumed', ['zone_id' => $zone->id]);
            $zone = $zone->fresh();
            
            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));
            
            return $zone;
        });
    }

    /**
     * Режим наполнения (Fill Mode)
     */
    public function fill(Zone $zone, array $data): array
    {
        // Используем history-logger для всех операций с нодами
        $baseUrl = config('services.history_logger.url');
        if (!$baseUrl) {
            throw new \DomainException('History Logger URL not configured');
        }
        
        $token = config('services.history_logger.token') ?? config('services.python_bridge.token'); // Fallback на старый токен
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];

        $payload = [
            'target_level' => $data['target_level'],
        ];
        if (isset($data['max_duration_sec'])) {
            $payload['max_duration_sec'] = $data['max_duration_sec'];
        }

        try {
            $response = \Illuminate\Support\Facades\Http::withHeaders($headers)
                ->timeout(350) // Больше чем max_duration_sec (300) + запас
                ->post("{$baseUrl}/zones/{$zone->id}/fill", $payload);

            if (!$response->successful()) {
                Log::error('ZoneService: Fill operation failed', [
                    'zone_id' => $zone->id,
                    'target_level' => $data['target_level'],
                    'status' => $response->status(),
                    'response' => substr($response->body(), 0, 500),
                ]);
                throw new \DomainException('Fill operation failed: ' . substr($response->body(), 0, 200));
            }

            Log::info('Zone fill executed', [
                'zone_id' => $zone->id,
                'target_level' => $data['target_level'],
            ]);

            return $response->json('data', []);
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('ZoneService: Connection error during fill', [
                'zone_id' => $zone->id,
                'target_level' => $data['target_level'],
                'error' => $e->getMessage(),
            ]);
            throw new \DomainException('Unable to connect to fill service. Please try again later.');
        } catch (\Illuminate\Http\Client\TimeoutException $e) {
            Log::error('ZoneService: Timeout error during fill', [
                'zone_id' => $zone->id,
                'target_level' => $data['target_level'],
                'error' => $e->getMessage(),
            ]);
            throw new \DomainException('Fill operation timed out. Please try again later.');
        } catch (\Illuminate\Http\Client\RequestException $e) {
            Log::error('ZoneService: Request error during fill', [
                'zone_id' => $zone->id,
                'target_level' => $data['target_level'],
                'error' => $e->getMessage(),
                'status' => $e->response?->status(),
            ]);
            throw new \DomainException('Fill operation failed. Please check the request parameters.');
        }
    }

    /**
     * Режим слива (Drain Mode)
     */
    public function drain(Zone $zone, array $data): array
    {
        // Используем history-logger для всех операций с нодами
        $baseUrl = config('services.history_logger.url');
        if (!$baseUrl) {
            throw new \DomainException('History Logger URL not configured');
        }
        
        $token = config('services.history_logger.token') ?? config('services.python_bridge.token'); // Fallback на старый токен
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];

        $payload = [
            'target_level' => $data['target_level'],
        ];
        if (isset($data['max_duration_sec'])) {
            $payload['max_duration_sec'] = $data['max_duration_sec'];
        }

        try {
            $response = \Illuminate\Support\Facades\Http::withHeaders($headers)
                ->timeout(350) // Больше чем max_duration_sec (300) + запас
                ->post("{$baseUrl}/zones/{$zone->id}/drain", $payload);

            if (!$response->successful()) {
                Log::error('ZoneService: Drain operation failed', [
                    'zone_id' => $zone->id,
                    'target_level' => $data['target_level'],
                    'status' => $response->status(),
                    'response' => substr($response->body(), 0, 500),
                ]);
                throw new \DomainException('Drain operation failed: ' . substr($response->body(), 0, 200));
            }

            Log::info('Zone drain executed', [
                'zone_id' => $zone->id,
                'target_level' => $data['target_level'],
            ]);

            return $response->json('data', []);
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('ZoneService: Connection error during drain', [
                'zone_id' => $zone->id,
                'target_level' => $data['target_level'],
                'error' => $e->getMessage(),
            ]);
            throw new \DomainException('Unable to connect to drain service. Please try again later.');
        } catch (\Illuminate\Http\Client\TimeoutException $e) {
            Log::error('ZoneService: Timeout error during drain', [
                'zone_id' => $zone->id,
                'target_level' => $data['target_level'],
                'error' => $e->getMessage(),
            ]);
            throw new \DomainException('Drain operation timed out. Please try again later.');
        } catch (\Illuminate\Http\Client\RequestException $e) {
            Log::error('ZoneService: Request error during drain', [
                'zone_id' => $zone->id,
                'target_level' => $data['target_level'],
                'error' => $e->getMessage(),
                'status' => $e->response?->status(),
            ]);
            throw new \DomainException('Drain operation failed. Please check the request parameters.');
        }
    }

    /**
     * Калибровка расхода воды
     */
    public function calibrateFlow(Zone $zone, array $data): array
    {
        // Используем history-logger для всех операций с нодами
        $baseUrl = config('services.history_logger.url');
        if (!$baseUrl) {
            throw new \DomainException('History Logger URL not configured');
        }
        
        $token = config('services.history_logger.token') ?? config('services.python_bridge.token'); // Fallback на старый токен
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];

        $payload = [
            'node_id' => $data['node_id'],
            'channel' => $data['channel'],
        ];
        if (isset($data['pump_duration_sec'])) {
            $payload['pump_duration_sec'] = $data['pump_duration_sec'];
        }

        try {
            $response = \Illuminate\Support\Facades\Http::withHeaders($headers)
                ->timeout(30) // Калибровка занимает ~12 секунд (10 сек насос + 2 сек ожидание)
                ->post("{$baseUrl}/zones/{$zone->id}/calibrate-flow", $payload);

            if (!$response->successful()) {
                Log::error('ZoneService: Flow calibration failed', [
                    'zone_id' => $zone->id,
                    'node_id' => $data['node_id'] ?? null,
                    'channel' => $data['channel'] ?? null,
                    'status' => $response->status(),
                    'response' => substr($response->body(), 0, 500),
                ]);
                throw new \DomainException('Flow calibration failed: ' . substr($response->body(), 0, 200));
            }

            Log::info('Flow calibration executed', [
                'zone_id' => $zone->id,
                'node_id' => $data['node_id'],
                'channel' => $data['channel'],
            ]);

            return $response->json('data', []);
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('ZoneService: Connection error during flow calibration', [
                'zone_id' => $zone->id,
                'node_id' => $data['node_id'] ?? null,
                'channel' => $data['channel'] ?? null,
                'error' => $e->getMessage(),
            ]);
            throw new \DomainException('Unable to connect to calibration service. Please try again later.');
        } catch (\Illuminate\Http\Client\TimeoutException $e) {
            Log::error('ZoneService: Timeout error during flow calibration', [
                'zone_id' => $zone->id,
                'node_id' => $data['node_id'] ?? null,
                'channel' => $data['channel'] ?? null,
                'error' => $e->getMessage(),
            ]);
            throw new \DomainException('Flow calibration timed out. Please try again later.');
        } catch (\Illuminate\Http\Client\RequestException $e) {
            Log::error('ZoneService: Request error during flow calibration', [
                'zone_id' => $zone->id,
                'node_id' => $data['node_id'] ?? null,
                'channel' => $data['channel'] ?? null,
                'error' => $e->getMessage(),
                'status' => $e->response?->status(),
            ]);
            throw new \DomainException('Flow calibration failed. Please check the request parameters.');
        }
    }

    /**
     * Завершить grow-cycle (harvest)
     */
    public function harvest(Zone $zone): Zone
    {
        return DB::transaction(function () use ($zone) {
            // Проверяем, что зона в статусе RUNNING или PAUSED
            if (!in_array($zone->status, ['RUNNING', 'PAUSED'])) {
                throw new \DomainException("Zone must be RUNNING or PAUSED to harvest. Current status: {$zone->status}");
            }

            // Обновляем статус зоны на HARVESTED
            $zone->update(['status' => 'HARVESTED']);
            
            // Закрываем активный recipe instance, если есть
            if ($zone->recipeInstance) {
                // Можно пометить instance как завершенный (добавить ended_at если есть колонка)
                // Или просто оставить как есть для истории
                Log::info('Recipe instance closed on harvest', [
                    'zone_id' => $zone->id,
                    'recipe_instance_id' => $zone->recipeInstance->id,
                ]);
            }

            // Создаем zone_event
            $hasPayloadJson = Schema::hasColumn('zone_events', 'payload_json');
            
            $eventPayload = json_encode([
                'zone_id' => $zone->id,
                'status' => 'HARVESTED',
                'harvested_at' => now()->toIso8601String(),
            ]);
            
            $eventData = [
                'zone_id' => $zone->id,
                'type' => 'CYCLE_HARVESTED',
                'created_at' => now(),
            ];
            
            if ($hasPayloadJson) {
                $eventData['payload_json'] = $eventPayload;
            } else {
                $eventData['details'] = $eventPayload;
            }
            
            DB::table('zone_events')->insert($eventData);

            Log::info('Zone cycle harvested', [
                'zone_id' => $zone->id,
            ]);

            $zone = $zone->fresh();
            
            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));
            
            return $zone;
        });
    }
}

