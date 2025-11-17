<?php

namespace App\Services;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Log;

class NodeConfigService
{
    /**
     * Генерировать полный NodeConfig для узла из данных БД.
     * 
     * @param DeviceNode $node
     * @param int|null $version Версия конфига (если не указана, используется текущая версия из БД или 1)
     * @return array
     */
    public function generateNodeConfig(DeviceNode $node, ?int $version = null): array
    {
        // Загружаем каналы узла
        $node->load('channels');
        
        // Определяем версию конфига
        if ($version === null) {
            // Берём версию из config узла или устанавливаем 1
            $nodeConfig = $node->config ?? [];
            $version = $nodeConfig['version'] ?? 1;
        }
        
        // Формируем channels
        $channels = [];
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
        
        // Формируем wifi конфигурацию
        $wifi = $this->getWifiConfig($node);
        
        // Формируем mqtt конфигурацию
        $mqtt = $this->getMqttConfig($node);
        
        $nodeConfig = [
            'node_id' => $node->uid,
            'version' => $version,
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
     * @return array
     */
    private function getWifiConfig(DeviceNode $node): array
    {
        // Проверяем config узла
        $nodeConfig = $node->config ?? [];
        if (isset($nodeConfig['wifi'])) {
            return $nodeConfig['wifi'];
        }
        
        // Используем глобальные настройки
        return [
            'ssid' => Config::get('services.wifi.ssid', 'HydroFarm'),
            'pass' => Config::get('services.wifi.password', ''),
        ];
    }
    
    /**
     * Получить MQTT конфигурацию для узла.
     * 
     * @param DeviceNode $node
     * @return array
     */
    private function getMqttConfig(DeviceNode $node): array
    {
        // Проверяем config узла
        $nodeConfig = $node->config ?? [];
        if (isset($nodeConfig['mqtt'])) {
            return $nodeConfig['mqtt'];
        }
        
        // Используем глобальные настройки MQTT
        return [
            'host' => Config::get('services.mqtt.host', 'mqtt'),
            'port' => Config::get('services.mqtt.port', 1883),
            'keepalive' => Config::get('services.mqtt.keepalive', 30),
        ];
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

