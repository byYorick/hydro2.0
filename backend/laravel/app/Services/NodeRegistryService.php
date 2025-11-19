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
     * @param string $nodeUid Уникальный идентификатор узла (MAC/UID)
     * @param string|null $zoneUid UID зоны для привязки (может быть zn-{id} или просто id)
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
            
            // Привязка к зоне, если указана
            if ($zoneUid) {
                $zoneId = $this->resolveZoneId($zoneUid);
                if ($zoneId) {
                    $node->zone_id = $zoneId;
                }
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
     * @param array $helloData Данные из node_hello:
     *   - hardware_id: string
     *   - node_type: string
     *   - fw_version: string|null
     *   - hardware_revision: string|null
     *   - capabilities: array
     *   - provisioning_meta: array {greenhouse_token, zone_id, node_name}
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
                $node->lifecycle_state = NodeLifecycleState::UNPROVISIONED;
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
            
            // Обработка greenhouse_token
            if (isset($provisioningMeta['greenhouse_token'])) {
                $greenhouseToken = $provisioningMeta['greenhouse_token'];
                $greenhouse = $this->findGreenhouseByToken($greenhouseToken);
                if ($greenhouse) {
                    // Если указана зона, привязываем к ней
                    $zoneId = $provisioningMeta['zone_id'] ?? null;
                    if ($zoneId) {
                        $zone = Zone::where('id', $zoneId)
                            ->where('greenhouse_id', $greenhouse->id)
                            ->first();
                        if ($zone) {
                            $node->zone_id = $zone->id;
                        }
                    }
                }
            }
            
            // Привязка к зоне напрямую (если zone_id указан без greenhouse_token)
            $zoneId = $provisioningMeta['zone_id'] ?? null;
            if ($zoneId && !$node->zone_id) {
                $zone = Zone::find($zoneId);
                if ($zone) {
                    $node->zone_id = $zone->id;
                }
            }
            
            // Устанавливаем lifecycle_state
            if (!$node->id) {
                // Новый узел
                if ($node->zone_id) {
                    $node->lifecycle_state = NodeLifecycleState::ASSIGNED_TO_ZONE;
                } else {
                    $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                }
            } else {
                // Существующий узел - обновляем состояние в зависимости от наличия зоны
                if ($node->zone_id && $node->lifecycle_state === NodeLifecycleState::REGISTERED_BACKEND) {
                    $node->lifecycle_state = NodeLifecycleState::ASSIGNED_TO_ZONE;
                }
            }
            
            // Отмечаем как validated
            $node->validated = true;
            
            $node->save();
            
            // Очищаем кеш списка устройств и статистики для всех пользователей
            // Кеш формируется как 'devices_list_' . auth()->id()
            // Очищаем кеш для всех пользователей (паттерн не поддерживается напрямую)
            // Используем flush, так как это редкое событие (регистрация узла)
            Cache::flush();
            
            Log::info('Node registered from node_hello', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'hardware_id' => $hardwareId,
                'zone_id' => $node->zone_id,
                'lifecycle_state' => $node->lifecycle_state?->value,
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
     * Найти теплицу по токену.
     * 
     * @param string $token Greenhouse token (может быть uid теплицы)
     * @return Greenhouse|null
     */
    private function findGreenhouseByToken(string $token): ?Greenhouse
    {
        // Пока упрощённая логика: ищем по uid
        // В будущем можно добавить отдельную таблицу для токенов
        return Greenhouse::where('uid', $token)->first();
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
