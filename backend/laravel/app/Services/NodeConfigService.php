<?php

namespace App\Services;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Enums\NodeLifecycleState;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Log;

class NodeConfigService
{
    /**
     * Генерировать полный NodeConfig для узла из данных БД.
     * 
     * @param DeviceNode $node
     * @param int|null $version Версия конфига (если не указана, используется текущая версия из БД или 1)
     * @param bool $includeCredentials Включать ли Wi-Fi пароли и MQTT креды (по умолчанию false для безопасности)
     * @param bool $isBindingMode true, если конфиг публикуется во время привязки (pending_zone_id установлена, zone_id ещё нет)
     * @return array
     */
    public function generateNodeConfig(DeviceNode $node, ?int $version = null, bool $includeCredentials = false, bool $isBindingMode = false): array
    {
        // Загружаем каналы узла и связанные данные
        $node->load(['channels', 'zone.greenhouse']);
        
        // Определяем версию конфига
        if ($version === null) {
            // Берём версию из config узла или устанавливаем 3 (текущая версия с gh_uid/zone_uid)
            $nodeConfig = $node->config ?? [];
            $version = $nodeConfig['version'] ?? 3;
        }
        
        // Получаем gh_uid и zone_uid из связанной зоны и теплицы
        $ghUid = 'gh-1'; // Значение по умолчанию
        $zoneUid = 'zn-1'; // Значение по умолчанию
        
        if ($node->zone) {
            $zoneUid = $node->zone->uid ?? 'zn-' . $node->zone->id;
            if ($node->zone->greenhouse) {
                $ghUid = $node->zone->greenhouse->uid ?? 'gh-' . $node->zone->greenhouse->id;
            }
        }
        
        // Формируем channels
        $channels = [];
        $isRelayNode = strtolower($node->type ?? '') === 'relay';

        // В режиме привязки для релейных нод отправляем временный конфиг,
        // чтобы прошивка корректно инициализировалась до ручной настройки каналов пользователем.
        if ($isBindingMode && $isRelayNode) {
            $channels = [
                [
                    'name' => 'relay1',
                    'type' => 'ACTUATOR',
                    'actuator_type' => 'RELAY',
                    'gpio' => 26, // временный GPIO, пользователь настроит реальные после привязки
                    'fail_safe_mode' => 'NO',
                ],
                [
                    'name' => 'relay2',
                    'type' => 'ACTUATOR',
                    'actuator_type' => 'RELAY',
                    'gpio' => 27,
                    'fail_safe_mode' => 'NO',
                ],
            ];
        } else {
            foreach ($node->channels as $channel) {
                $channelData = [
                    'name' => $channel->channel,
                    'type' => $this->normalizeChannelType($channel->type),
                    'metric' => $channel->metric,
                ];
                
                // Добавляем дополнительные параметры из config канала
                $channelConfig = $channel->config ?? [];
                if (!empty($channelConfig)) {
                    // Объединяем с базовыми параметрами
                    $channelData = array_merge($channelData, $channelConfig);
                }
                
                // Добавляем стандартные параметры, если их нет
                if ($channelData['type'] === 'SENSOR' && !isset($channelData['poll_interval_ms'])) {
                    $channelData['poll_interval_ms'] = 3000; // По умолчанию 3 секунды
                }
                
                if ($channelData['type'] === 'ACTUATOR') {
                    if (!isset($channelData['actuator_type'])) {
                        $channelData['actuator_type'] = $this->inferActuatorType($channel->channel);
                    }
                    if (!isset($channelData['safe_limits'])) {
                        $channelData['safe_limits'] = [
                            'max_duration_ms' => 5000,
                            'min_off_ms' => 3000,
                        ];
                    }
                }
                
                $channels[] = $channelData;
            }
        }
        
        // Формируем wifi конфигурацию
        $wifi = $this->getWifiConfig($node, $includeCredentials);
        
        // Формируем mqtt конфигурацию
        $mqtt = $this->getMqttConfig($node, $includeCredentials);
        
        $nodeConfig = [
            'node_id' => $node->uid,
            'version' => $version,
            'type' => $node->type ?? 'unknown',
            'gh_uid' => $ghUid,
            'zone_uid' => $zoneUid,
            'channels' => $channels,
            'wifi' => $wifi,
            'mqtt' => $mqtt,
        ];
        
        // Валидация конфига перед возвратом
        $this->validateNodeConfig($nodeConfig);
        
        return $nodeConfig;
    }
    
    /**
     * Нормализовать тип канала.
     * 
     * @param string|null $type
     * @return string
     */
    private function normalizeChannelType(?string $type): string
    {
        if (!$type) {
            return 'SENSOR';
        }
        
        $typeUpper = strtoupper($type);
        if (in_array($typeUpper, ['SENSOR', 'ACTUATOR'])) {
            return $typeUpper;
        }
        
        // Маппинг старых значений
        if (in_array($typeUpper, ['S', 'SENSOR'])) {
            return 'SENSOR';
        }
        if (in_array($typeUpper, ['A', 'ACTUATOR', 'ACT'])) {
            return 'ACTUATOR';
        }
        
        return 'SENSOR'; // По умолчанию
    }
    
    /**
     * Определить тип актуатора по имени канала.
     * 
     * @param string $channelName
     * @return string
     */
    private function inferActuatorType(string $channelName): string
    {
        $nameLower = strtolower($channelName);
        
        if (str_contains($nameLower, 'pump')) {
            return 'PUMP';
        }
        if (str_contains($nameLower, 'valve') || str_contains($nameLower, 'solenoid')) {
            return 'VALVE';
        }
        if (str_contains($nameLower, 'relay')) {
            return 'RELAY';
        }
        if (str_contains($nameLower, 'light') || str_contains($nameLower, 'led')) {
            return 'LIGHT';
        }
        
        return 'ACTUATOR'; // По умолчанию
    }
    
    /**
     * Получить WiFi конфигурацию для узла.
     * 
     * @param DeviceNode $node
     * @param bool $includeCredentials Включать ли пароль (по умолчанию false для безопасности)
     * @return array
     */
    private function getWifiConfig(DeviceNode $node, bool $includeCredentials = false): array
    {
        // Для API запросов (includeCredentials = false) не возвращаем Wi-Fi конфигурацию
        // Это предотвращает утечку SSID и паролей через API
        if (!$includeCredentials) {
            // Возвращаем минимальную информацию для API
            return [
                'configured' => true, // Указываем, что Wi-Fi настроен, но не раскрываем детали
            ];
        }
        
        // Для публикации конфига через MQTT (includeCredentials = true)
        // ВАЖНО: Если нода отправила node_hello и зарегистрирована (hasWorkingConnection),
        // значит у неё уже есть рабочие Wi-Fi настройки.
        // Отправляем только {"configured": true}, чтобы прошивка не перезаписывала существующие настройки.
        // Это предотвращает переподключение Wi-Fi, если нода уже работает.
        $lifecycleState = $node->lifecycleState();
        
        if ($lifecycleState->hasWorkingConnection()) {
            // Нода уже подключена к WiFi (иначе не смогла бы отправить node_hello)
            // Не отправляем полную конфигурацию Wi-Fi, чтобы прошивка не перезаписывала существующие настройки
            Log::info('NodeConfigService: Node already connected, sending wifi={"configured": true} to preserve existing settings', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'lifecycle_state' => $lifecycleState->value,
            ]);
            return [
                'configured' => true, // Прошивка не будет перезаписывать Wi-Fi настройки
            ];
        }
        
        // Нода еще не подключена - отправляем полную конфигурацию Wi-Fi
        // Проверяем, есть ли сохраненная конфигурация Wi-Fi в node->config
        $nodeConfig = $node->config ?? [];
        if (isset($nodeConfig['wifi']) && is_array($nodeConfig['wifi'])) {
            // Если в node->config есть Wi-Fi конфигурация, используем её
            // (это может быть конфигурация, сохраненная после setup режима)
            $wifiConfig = $nodeConfig['wifi'];
            // Если в конфиге есть только "configured", не добавляем ssid/pass
            if (isset($wifiConfig['configured']) && count($wifiConfig) === 1) {
                return $wifiConfig;
            }
            // Если есть ssid/pass, возвращаем их
            return $wifiConfig;
        }
        
        // Используем глобальные настройки только для новых нод
        Log::info('NodeConfigService: Node not connected yet, sending full wifi config', [
            'node_id' => $node->id,
            'uid' => $node->uid,
            'lifecycle_state' => $lifecycleState->value,
        ]);
        return [
            'ssid' => Config::get('services.wifi.ssid', 'HydroFarm'),
            'pass' => Config::get('services.wifi.password', ''),
        ];
    }
    
    /**
     * Получить MQTT конфигурацию для узла.
     * 
     * @param DeviceNode $node
     * @param bool $includeCredentials Включать ли чувствительные параметры (по умолчанию false для безопасности)
     * @return array
     */
    private function getMqttConfig(DeviceNode $node, bool $includeCredentials = false): array
    {
        // Для API запросов (includeCredentials = false) не возвращаем MQTT конфигурацию
        // Это предотвращает утечку MQTT креденшалов через API
        if (!$includeCredentials) {
            // Возвращаем минимальную информацию для API
            return [
                'configured' => true, // Указываем, что MQTT настроен, но не раскрываем детали
            ];
        }
        
        // Для публикации конфига через MQTT (includeCredentials = true)
        // ВАЖНО: Если нода отправила node_hello и зарегистрирована (REGISTERED_BACKEND или выше),
        // значит у неё уже есть рабочие MQTT настройки.
        // Отправляем только {"configured": true}, чтобы прошивка не перезаписывала существующие настройки.
        $lifecycleState = $node->lifecycleState();
        
        // Проверяем, что нода в одном из состояний, когда она уже подключена к MQTT
        $isAlreadyConnected = in_array($lifecycleState, [
            NodeLifecycleState::REGISTERED_BACKEND,
            NodeLifecycleState::ASSIGNED_TO_ZONE,
            NodeLifecycleState::ACTIVE,
            NodeLifecycleState::DEGRADED,
        ]);
        
        if ($isAlreadyConnected) {
            // Нода уже подключена к MQTT (иначе не смогла бы отправить node_hello)
            // Не отправляем полную конфигурацию MQTT, чтобы прошивка не перезаписывала существующие настройки
            Log::info('NodeConfigService: Node already connected, sending mqtt={"configured": true} to preserve existing settings', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'lifecycle_state' => $lifecycleState->value,
            ]);
            return [
                'configured' => true, // Прошивка не будет перезаписывать MQTT настройки
            ];
        }
        
        // Нода еще не подключена - отправляем полную конфигурацию MQTT
        // Используем глобальные настройки MQTT
        // ВАЖНО: port и keepalive должны быть числами, а не строками (для валидации в прошивке)
        Log::info('NodeConfigService: Node not connected yet, sending full MQTT config', [
            'node_id' => $node->id,
            'uid' => $node->uid,
            'lifecycle_state' => $lifecycleState->value,
        ]);
        
        $mqtt = [
            'host' => Config::get('services.mqtt.host', 'mqtt'),
            'port' => (int) Config::get('services.mqtt.port', 1883), // Явно приводим к int
            'keepalive' => (int) Config::get('services.mqtt.keepalive', 30), // Явно приводим к int
        ];
        
        // Включаем чувствительные параметры
        if ($includeCredentials) {
            $mqtt['username'] = Config::get('services.mqtt.username');
            $mqtt['password'] = Config::get('services.mqtt.password');
            $mqtt['client_id'] = Config::get('services.mqtt.client_id');
        }
        
        // Если в $node->config есть mqtt секция, мержим её с глобальными настройками
        // Это позволяет переопределить некоторые параметры на уровне узла
        $nodeConfig = $node->config ?? [];
        if (isset($nodeConfig['mqtt']) && is_array($nodeConfig['mqtt'])) {
            $mqtt = array_merge($mqtt, $nodeConfig['mqtt']);
            // Убеждаемся, что port и keepalive остаются числами после мержа
            if (isset($mqtt['port'])) {
                $mqtt['port'] = (int) $mqtt['port'];
            }
            if (isset($mqtt['keepalive'])) {
                $mqtt['keepalive'] = (int) $mqtt['keepalive'];
            }
        }
        
        return $mqtt;
    }
    
    /**
     * Валидировать NodeConfig перед отправкой.
     * 
     * @param array $config
     * @return void
     * @throws \InvalidArgumentException
     */
    private function validateNodeConfig(array $config): void
    {
        if (empty($config['node_id'])) {
            throw new \InvalidArgumentException('NodeConfig must have node_id');
        }
        
        if (!isset($config['version']) || $config['version'] < 1) {
            throw new \InvalidArgumentException('NodeConfig must have valid version');
        }
        
        if (empty($config['gh_uid'])) {
            throw new \InvalidArgumentException('NodeConfig must have gh_uid');
        }
        
        if (empty($config['zone_uid'])) {
            throw new \InvalidArgumentException('NodeConfig must have zone_uid');
        }
        
        if (!is_array($config['channels'] ?? null)) {
            throw new \InvalidArgumentException('NodeConfig must have channels array');
        }
        
        if (!is_array($config['wifi'] ?? null)) {
            throw new \InvalidArgumentException('NodeConfig must have wifi config');
        }
        
        if (!is_array($config['mqtt'] ?? null)) {
            throw new \InvalidArgumentException('NodeConfig must have mqtt config');
        }
    }
}
