<?php

namespace App\Services;

use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * Best-effort сброс MQTT namespace на устройстве при detach.
 *
 * Публикует NodeConfig с gh_uid=gh-temp / zone_uid=zn-temp в текущий zone-топик
 * через history-logger. Firmware (node_config_handler) применяет такой конфиг,
 * когда нода ещё не в temp-режиме, и переключает NVS/MQTT на preconfig namespace.
 *
 * Не блокирует detach при offline/ошибке HL: history-logger и так дропает
 * телеметрию unassigned-ноды (infra_telemetry_node_unassigned).
 */
class NodeFirmwareUnbindService
{
    public const TEMP_GH_UID = 'gh-temp';

    public const TEMP_ZONE_UID = 'zn-temp';

    public function __construct(
        private readonly NodeConfigService $configService,
    ) {}

    /**
     * Опубликовать unbind-конфиг на текущий zone-топик ноды.
     *
     * @param  int|null  $boundZoneId  Zone id для маршрутизации топика (нужен, если zone_id уже очищен в БД)
     */
    public function publishTempNamespaceConfig(DeviceNode $node, ?int $boundZoneId = null): bool
    {
        $zoneId = $boundZoneId ?? $node->zone_id;
        if (! $zoneId) {
            Log::debug('NodeFirmwareUnbindService: skip — no bound zone', [
                'node_id' => $node->id,
                'uid' => $node->uid,
            ]);

            return false;
        }

        $zone = Zone::with('greenhouse')->find($zoneId);
        if (! $zone || ! $zone->greenhouse) {
            Log::warning('NodeFirmwareUnbindService: cannot resolve zone/greenhouse for unbind', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'zone_id' => $zoneId,
            ]);

            return false;
        }

        $baseUrl = Config::get('services.history_logger.url');
        if (! is_string($baseUrl) || $baseUrl === '') {
            Log::warning('NodeFirmwareUnbindService: history-logger URL not configured', [
                'node_id' => $node->id,
                'uid' => $node->uid,
            ]);

            return false;
        }

        $config = $this->buildUnbindConfig($node);
        $greenhouseUid = $zone->greenhouse->uid;
        $zoneUid = $zone->uid;

        $headers = [];
        $token = Config::get('services.history_logger.token') ?? Config::get('services.python_bridge.token');
        if (is_string($token) && $token !== '') {
            $headers['Authorization'] = "Bearer {$token}";
        }

        $requestData = [
            'zone_id' => $zoneId,
            'greenhouse_uid' => $greenhouseUid,
            'zone_uid' => $zoneUid,
            'config' => $config,
        ];

        try {
            $response = Http::withHeaders($headers)
                ->timeout(10)
                ->acceptJson()
                ->post("{$baseUrl}/nodes/{$node->uid}/config", $requestData);

            if (! $response->successful()) {
                Log::warning('NodeFirmwareUnbindService: HL rejected unbind config publish', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'zone_id' => $zoneId,
                    'status' => $response->status(),
                    'body' => substr($response->body(), 0, 500),
                ]);

                return false;
            }

            Log::info('NodeFirmwareUnbindService: unbind config published', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'zone_id' => $zoneId,
                'zone_uid' => $zoneUid,
                'greenhouse_uid' => $greenhouseUid,
                'config_gh_uid' => self::TEMP_GH_UID,
                'config_zone_uid' => self::TEMP_ZONE_UID,
            ]);

            return true;
        } catch (\Throwable $e) {
            Log::warning('NodeFirmwareUnbindService: failed to publish unbind config', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return false;
        }
    }

    /**
     * @return array<string, mixed>
     */
    public function buildUnbindConfig(DeviceNode $node): array
    {
        $config = $this->configService->generateNodeConfig($node, null, true, false);

        if (empty($config['node_id'])) {
            $config['node_id'] = $node->uid;
        }
        if (empty($config['type'])) {
            $config['type'] = $node->type;
        }
        if (! isset($config['version']) || ! is_numeric($config['version'])) {
            $config['version'] = 3;
        }
        if (! isset($config['channels']) || ! is_array($config['channels'])) {
            $config['channels'] = [];
        }
        if (! isset($config['mqtt']) || ! is_array($config['mqtt'])) {
            // Placeholder: firmware сохраняет текущие MQTT-настройки и всё равно
            // перезапускает менеджер из-за смены gh_uid/zone_uid.
            $config['mqtt'] = ['configured' => true];
        }

        $config['gh_uid'] = self::TEMP_GH_UID;
        $config['zone_uid'] = self::TEMP_ZONE_UID;

        return $config;
    }

    /**
     * Зеркалирует temp namespace в nodes.config (read-model), без публикации.
     */
    public function mirrorTempNamespaceInStoredConfig(DeviceNode $node): void
    {
        $config = is_array($node->config) ? $node->config : [];
        $config['gh_uid'] = self::TEMP_GH_UID;
        $config['zone_uid'] = self::TEMP_ZONE_UID;
        if (empty($config['node_id'])) {
            $config['node_id'] = $node->uid;
        }
        $node->config = $config;
    }
}
