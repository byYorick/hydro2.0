<?php

namespace App\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Zone;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class NodeRegistryService
{
    /**
     * Зарегистрировать узел в системе.
     * 
     * Если узел уже существует, обновляет его атрибуты.
     * Если узел новый, создаёт его и отмечает как validated.
     * 
     * ВАЖНО: Автопривязка к зоне отключена. Привязка должна происходить только
     * через явное действие пользователя (кнопка "Привязать" в UI).
     * 
     * @param string $nodeUid Уникальный идентификатор узла (MAC/UID)
     * @param string|null $zoneUid UID зоны (игнорируется, оставлен для обратной совместимости)
     * @param array $attributes Дополнительные атрибуты (firmware_version, hardware_revision и т.д.)
     * @return DeviceNode
     */
    public function registerNode(
        string $nodeUid,
        ?string $zoneUid = null,
        array $attributes = []
    ): DeviceNode {
        return DB::transaction(function () use ($nodeUid, $zoneUid, $attributes) {
            // Находим или создаём узел
            $node = DeviceNode::firstOrNew(['uid' => $nodeUid]);
            
            // КРИТИЧНО: Автопривязка к зоне при регистрации УДАЛЕНА
            // Привязка должна происходить только после явного действия пользователя (нажатие кнопки "Привязать")
            // Если указан zoneUid, игнорируем его и логируем предупреждение
            if ($zoneUid) {
                Log::warning('Node registration: zoneUid provided but auto-binding is disabled. Node will remain unbound until user manually attaches it.', [
                    'node_uid' => $nodeUid,
                    'requested_zone_uid' => $zoneUid,
                    'ip' => request()->ip(),
                ]);
            }
            
            // Обновляем атрибуты
            if (isset($attributes['firmware_version'])) {
                $node->fw_version = $attributes['firmware_version'];
            }
            
            if (isset($attributes['hardware_revision'])) {
                $node->hardware_revision = $attributes['hardware_revision'];
            }
            
            if (isset($attributes['name'])) {
                $node->name = $attributes['name'];
            }
            
            if (isset($attributes['type'])) {
                $node->type = $attributes['type'];
            }
            
            // Обновляем hardware_id, если указан
            if (isset($attributes['hardware_id'])) {
                $node->hardware_id = $attributes['hardware_id'];
            }
            
            // Устанавливаем first_seen_at при первом появлении
            // Проверяем через id, так как firstOrNew создаёт модель, но не сохраняет её
            if (!$node->id || !$node->first_seen_at) {
                $node->first_seen_at = now();
            }
            
            // Отмечаем как validated
            $node->validated = true;
            
            // Устанавливаем lifecycle_state в REGISTERED_BACKEND при регистрации
            if (!$node->id || !$node->lifecycle_state) {
                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
            }
            
            $node->save();
            
            Log::info('Node registered', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'zone_id' => $node->zone_id,
                'validated' => $node->validated,
                'lifecycle_state' => $node->lifecycle_state?->value,
            ]);
            
            return $node;
        });
    }
    
    /**
     * Зарегистрировать узел из node_hello сообщения (MQTT).
     * 
     * ВАЖНО: Автопривязка к зоне отключена. Даже если в provisioning_meta указаны
     * greenhouse_token и zone_id, они игнорируются. Привязка должна происходить только
     * через явное действие пользователя (кнопка "Привязать" в UI).
     * 
     * @param array $helloData Данные из node_hello:
     *   - hardware_id: string
     *   - node_type: string
     *   - fw_version: string|null
     *   - hardware_revision: string|null
     *   - capabilities: array
     *   - provisioning_meta: array {greenhouse_token (игнорируется), zone_id (игнорируется), node_name}
     * @return DeviceNode
     */
    public function registerNodeFromHello(array $helloData): DeviceNode
    {
        return DB::transaction(function () use ($helloData) {
            $hardwareId = $helloData['hardware_id'] ?? null;
            if (!$hardwareId) {
                throw new \InvalidArgumentException('hardware_id is required');
            }
            
            // Ищем узел по hardware_id
            $node = DeviceNode::where('hardware_id', $hardwareId)->first();
            
            // Если узел не найден, создаём новый
            if (!$node) {
                // Генерируем uid на основе hardware_id и типа узла
                $nodeType = $helloData['node_type'] ?? 'unknown';
                $uid = $this->generateNodeUid($hardwareId, $nodeType);
                
                // Проверяем уникальность uid
                $counter = 1;
                while (DeviceNode::where('uid', $uid)->exists()) {
                    $uid = $this->generateNodeUid($hardwareId, $nodeType, $counter);
                    $counter++;
                }
                
                $node = new DeviceNode();
                $node->uid = $uid;
                $node->hardware_id = $hardwareId;
                $node->type = $nodeType;
                $node->first_seen_at = now();
                // Новые ноды с временными конфигами регистрируются как REGISTERED_BACKEND
                // Когда нода получит реальные конфиги и будет привязана к зоне, состояние изменится на ASSIGNED_TO_ZONE
                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
            }
            
            // Обновляем атрибуты
            if (isset($helloData['fw_version'])) {
                $node->fw_version = $helloData['fw_version'];
            }
            
            if (isset($helloData['hardware_revision'])) {
                $node->hardware_revision = $helloData['hardware_revision'];
            }
            
            // Обработка provisioning_meta
            $provisioningMeta = $helloData['provisioning_meta'] ?? [];
            
            if (isset($provisioningMeta['node_name'])) {
                $node->name = $provisioningMeta['node_name'];
            }
            
            // КРИТИЧНО: Автопривязка к зоне через greenhouse_token УДАЛЕНА
            // Привязка должна происходить только после явного действия пользователя (нажатие кнопки "Привязать")
            // Если указан greenhouse_token или zone_id, игнорируем их и логируем предупреждение
            if (isset($provisioningMeta['greenhouse_token']) || isset($provisioningMeta['zone_id'])) {
                Log::info('Node registration: provisioning_meta contains greenhouse_token or zone_id, but auto-binding is disabled. Node will remain unbound until user manually attaches it.', [
                    'node_id' => $node->id,
                    'hardware_id' => $hardwareId,
                    'has_greenhouse_token' => isset($provisioningMeta['greenhouse_token']),
                    'has_zone_id' => isset($provisioningMeta['zone_id']),
                    'zone_id' => $provisioningMeta['zone_id'] ?? null,
                ]);
            }
            
            // Устанавливаем lifecycle_state
            // Всегда оставляем REGISTERED_BACKEND - переход в ASSIGNED_TO_ZONE произойдет
            // только после успешной публикации конфига через PublishNodeConfigOnUpdate
            if (!$node->id || !$node->lifecycle_state) {
                // Новый узел - всегда REGISTERED_BACKEND, даже если есть zone_id
                // (нода с временными конфигами еще не привязана к реальной зоне)
                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
            }
            // Для существующих узлов не меняем lifecycle_state здесь
            // Переход в ASSIGNED_TO_ZONE произойдет только после успешной публикации конфига
            
            // Отмечаем как validated
            $node->validated = true;
            
            $node->save();
            
            // Создаём каналы из capabilities
            $this->syncNodeChannelsFromCapabilities($node, $helloData['capabilities'] ?? []);
            
            // Очищаем кеш списка устройств и статистики для всех пользователей
            // Вместо Cache::flush() используем более безопасную очистку только связанных ключей
            // Это предотвращает DoS через частые node_hello запросы
            // Очищаем только кеш, связанный с устройствами
            $cachePrefixes = ['devices_list_', 'nodes_list_', 'node_stats_'];
            foreach ($cachePrefixes as $prefix) {
                // Laravel Cache не поддерживает поиск по префиксу напрямую
                // Используем tags, если они доступны, или ограничиваем очистку
                // В production лучше использовать Redis с поддержкой SCAN
                if (config('cache.default') === 'redis') {
                    // Для Redis можно использовать более точную очистку через tags
                    // Но пока просто не очищаем весь кеш - это безопаснее
                    // Кеш устареет естественным образом через TTL
                    Log::debug('NodeRegistryService: Skipping cache flush for security', [
                        'node_id' => $node->id,
                        'cache_driver' => config('cache.default'),
                    ]);
                } else {
                    // Для других драйверов кеша не очищаем глобально
                    // Кеш устареет естественным образом
                    Log::debug('NodeRegistryService: Skipping cache flush for security', [
                        'node_id' => $node->id,
                        'cache_driver' => config('cache.default'),
                    ]);
                }
            }
            
            Log::info('Node registered from node_hello', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'hardware_id' => $hardwareId,
                'zone_id' => $node->zone_id,
                'lifecycle_state' => $node->lifecycle_state?->value,
                'channels_count' => $node->channels()->count(),
            ]);
            
            return $node;
        });
    }
    
    /**
     * Генерировать uid для узла на основе hardware_id и типа.
     * 
     * @param string $hardwareId
     * @param string $nodeType
     * @param int $counter Для уникальности, если uid уже существует
     * @return string
     */
    private function generateNodeUid(string $hardwareId, string $nodeType, int $counter = 0): string
    {
        // Используем первые 8 символов hardware_id и тип узла
        $shortId = substr(str_replace([':', '-', '_'], '', $hardwareId), 0, 8);
        
        // Определяем префикс типа узла
        $typePrefix = 'node';
        if ($nodeType === 'ph') {
            $typePrefix = 'ph';
        } elseif ($nodeType === 'ec') {
            $typePrefix = 'ec';
        } elseif ($nodeType === 'climate') {
            $typePrefix = 'clim';
        } elseif (in_array($nodeType, ['irrig', 'pump'])) {
            $typePrefix = 'irr';
        } elseif ($nodeType === 'light') {
            $typePrefix = 'light';
        }
        
        $uid = "nd-{$typePrefix}-{$shortId}";
        if ($counter > 0) {
            $uid .= "-{$counter}";
        }
        
        return $uid;
    }
    
    /**
     * Синхронизировать каналы узла из capabilities.
     * 
     * @param DeviceNode $node Узел
     * @param array $capabilities Массив строк capabilities (например: ["temperature", "humidity", "co2"])
     * @return void
     */
    private function syncNodeChannelsFromCapabilities(DeviceNode $node, array $capabilities): void
    {
        if (empty($capabilities)) {
            Log::debug('NodeRegistryService: No capabilities provided, skipping channel sync', [
                'node_id' => $node->id,
            ]);
            return;
        }
        
        // Маппинг capability -> channel configuration
        $capabilityConfig = [
            'temperature' => ['type' => 'sensor', 'metric' => 'TEMP_AIR', 'unit' => '°C'],
            'humidity' => ['type' => 'sensor', 'metric' => 'HUMIDITY', 'unit' => '%'],
            'co2' => ['type' => 'sensor', 'metric' => 'CO2', 'unit' => 'ppm'],
            'lighting' => ['type' => 'actuator', 'metric' => 'LIGHT', 'unit' => ''],
            'ventilation' => ['type' => 'actuator', 'metric' => 'VENTILATION', 'unit' => ''],
            'ph_sensor' => ['type' => 'sensor', 'metric' => 'PH', 'unit' => 'pH'],
            'ec_sensor' => ['type' => 'sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
            'pump_A' => ['type' => 'actuator', 'metric' => 'PUMP_A', 'unit' => ''],
            'pump_B' => ['type' => 'actuator', 'metric' => 'PUMP_B', 'unit' => ''],
            'pump_C' => ['type' => 'actuator', 'metric' => 'PUMP_C', 'unit' => ''],
            'pump_D' => ['type' => 'actuator', 'metric' => 'PUMP_D', 'unit' => ''],
        ];
        
        foreach ($capabilities as $capability) {
            if (!is_string($capability)) {
                Log::warning('NodeRegistryService: Invalid capability type', [
                    'node_id' => $node->id,
                    'capability' => $capability,
                ]);
                continue;
            }
            
            $config = $capabilityConfig[$capability] ?? [
                'type' => 'sensor',
                'metric' => strtoupper($capability),
                'unit' => '',
            ];
            
            // Создаём или обновляем канал
            \App\Models\NodeChannel::updateOrCreate(
                [
                    'node_id' => $node->id,
                    'channel' => $capability,
                ],
                [
                    'type' => $config['type'],
                    'metric' => $config['metric'],
                    'unit' => $config['unit'],
                    'config' => [],
                ]
            );
            
            Log::debug('NodeRegistryService: Channel synced from capability', [
                'node_id' => $node->id,
                'capability' => $capability,
                'channel_type' => $config['type'],
            ]);
        }
    }
    
    /**
     * Найти теплицу по токену.
     * 
     * @param string $token Greenhouse provisioning_token (секретный токен, не uid!)
     * @return Greenhouse|null
     */
    private function findGreenhouseByToken(string $token): ?Greenhouse
    {
        // Ищем по provisioning_token (секретный токен, не публичный uid)
        // Это предотвращает регистрацию нод в чужие теплицы, т.к. uid доступен всем viewer'ам
        return Greenhouse::where('provisioning_token', $token)->first();
    }
    
    /**
     * Разрешить zone_uid в zone_id.
     * 
     * @param string $zoneUid Может быть в формате "zn-1" или просто "1"
     * @return int|null
     */
    private function resolveZoneId(string $zoneUid): ?int
    {
        // Если формат zn-{id}
        if (str_starts_with($zoneUid, 'zn-')) {
            $zoneIdStr = substr($zoneUid, 3);
            if (is_numeric($zoneIdStr)) {
                // Проверяем, существует ли зона
                $zone = Zone::find((int)$zoneIdStr);
                return $zone?->id;
            }
        }
        
        // Если это просто число
        if (is_numeric($zoneUid)) {
            $zone = Zone::find((int)$zoneUid);
            return $zone?->id;
        }
        
        // В будущем можно добавить поиск по uid, если он появится в таблице zones
        return null;
    }
}
