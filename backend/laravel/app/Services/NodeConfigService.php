<?php

namespace App\Services;

use App\Models\DeviceNode;

class NodeConfigService
{
    /**
     * Получить сохраненный NodeConfig из базы.
     *
     * @param DeviceNode $node
     * @param bool $includeCredentials Включать ли чувствительные данные (по умолчанию false)
     * @return array
     */
    public function getStoredConfig(DeviceNode $node, bool $includeCredentials = false): array
    {
        $config = is_array($node->config) ? $node->config : [];
        if (empty($config)) {
            return [];
        }

        return $this->sanitizeConfig($config, $includeCredentials);
    }

    private function sanitizeConfig(array $config, bool $includeCredentials): array
    {
        if (! $includeCredentials) {
            if (array_key_exists('wifi', $config)) {
                $config['wifi'] = ['configured' => true];
            }

            if (array_key_exists('mqtt', $config)) {
                $config['mqtt'] = ['configured' => true];
            }
        }

        if (isset($config['channels']) && is_array($config['channels'])) {
            $config['channels'] = array_map(function ($entry) {
                return is_array($entry) ? $this->stripForbiddenChannelFields($entry) : $entry;
            }, $config['channels']);
        }

        return $config;
    }

    private function stripForbiddenChannelFields(array $config): array
    {
        unset($config['gpio'], $config['pin']);

        foreach ($config as $key => $value) {
            if (is_array($value)) {
                $config[$key] = $this->stripForbiddenChannelFields($value);
            }
        }

        return $config;
    }
}
