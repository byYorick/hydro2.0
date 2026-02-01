<?php

namespace App\Services;

use App\Models\DeviceNode;

class NodeConfigService
{
    /**
     * Сформировать NodeConfig для отправки ноде.
     *
     * @param DeviceNode $node
     * @param array<int, array<string, mixed>>|null $overrideChannels
     * @param bool $includeCredentials
     * @param bool $isNodeBinding
     * @return array<string, mixed>
     */
    public function generateNodeConfig(
        DeviceNode $node,
        ?array $overrideChannels = null,
        bool $includeCredentials = false,
        bool $isNodeBinding = false
    ): array {
        $config = $this->getStoredConfig($node, $includeCredentials);

        if (empty($config)) {
            $config = [
                'node_id' => $node->uid,
                'version' => 1,
                'type' => $node->type,
                'channels' => [],
            ];
        }

        if ($overrideChannels !== null) {
            $config['channels'] = $overrideChannels;
        } elseif (! isset($config['channels']) || ! is_array($config['channels'])) {
            $config['channels'] = $this->buildChannelsFromNode($node);
        }

        $config['version'] = $config['version'] ?? 1;
        if ($includeCredentials) {
            $nodeSecret = $config['node_secret'] ?? null;
            if (! is_string($nodeSecret) || $nodeSecret === '') {
                $config['node_secret'] = config('app.node_default_secret') ?? config('app.key');
            }
        }

        return $config;
    }

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

            unset($config['node_secret']);
        } else {
            $nodeSecret = $config['node_secret'] ?? null;
            if (! is_string($nodeSecret) || $nodeSecret === '') {
                $config['node_secret'] = config('app.node_default_secret') ?? config('app.key');
            }
        }

        if (isset($config['channels']) && is_array($config['channels'])) {
            $config['channels'] = array_map(function ($entry) {
                return is_array($entry) ? $this->stripForbiddenChannelFields($entry) : $entry;
            }, $config['channels']);
        }

        return $config;
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    private function buildChannelsFromNode(DeviceNode $node): array
    {
        $channels = $node->relationLoaded('channels') ? $node->channels : $node->channels()->get();

        return $channels->map(function ($channel) {
            $base = [
                'name' => $channel->channel,
                'channel' => $channel->channel,
                'type' => $channel->type,
                'metric' => $channel->metric,
                'unit' => $channel->unit,
            ];
            $extra = is_array($channel->config) ? $channel->config : [];
            $merged = array_merge($extra, array_filter($base, static fn ($value) => $value !== null));

            return $this->stripForbiddenChannelFields($merged);
        })->values()->all();
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
