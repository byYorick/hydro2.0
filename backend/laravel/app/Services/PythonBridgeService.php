<?php

namespace App\Services;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class PythonBridgeService
{
    public function sendZoneCommand(Zone $zone, array $payload): string
    {
        $cmdId = Str::uuid()->toString();
        $command = Command::create([
            'zone_id' => $zone->id,
            'cmd' => $payload['type'] ?? ($payload['cmd'] ?? 'unknown'),
            'params' => $payload['params'] ?? [],
            'status' => 'pending',
            'cmd_id' => $cmdId,
        ]);
        $ghUid = optional($zone->greenhouse)->uid ?? 'gh-1';
        
        // Get default node_uid and channel from zone if not provided
        $nodeUid = $payload['node_uid'] ?? null;
        $channel = $payload['channel'] ?? null;
        
        if (!$nodeUid || !$channel) {
            // Try to get first node and channel from zone
            $firstNode = DeviceNode::where('zone_id', $zone->id)->first();
            if ($firstNode) {
                $nodeUid = $nodeUid ?? $firstNode->uid;
                if (!$channel) {
                    // Get first channel from node
                    $firstChannel = $firstNode->channels()->first();
                    $channel = $firstChannel ? $firstChannel->channel : 'default';
                }
            }
        }
        
        // Fallback values if still not set
        $nodeUid = $nodeUid ?? 'default';
        $channel = $channel ?? 'default';
        
        $baseUrl = Config::get('services.python_bridge.base_url');
        $token = Config::get('services.python_bridge.token');
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];
        // Ensure params is an associative array (dict), not a list
        // Python service expects Dict[str, Any], not a list
        // Empty array [] serializes to [] in JSON, but we need {} for Python
        $params = $command->params ?? [];
        if (is_array($params) && array_is_list($params)) {
            // Convert indexed array to empty object (will serialize as {} in JSON)
            $params = new \stdClass();
        } elseif (empty($params) && is_array($params)) {
            // Empty associative array - convert to object to ensure {} in JSON
            $params = new \stdClass();
        }
        
        Http::withHeaders($headers)->post("{$baseUrl}/bridge/zones/{$zone->id}/commands", [
            'type' => $command->cmd,
            'params' => $params,
            'greenhouse_uid' => $ghUid,
            'node_uid' => $nodeUid,
            'channel' => $channel,
            'cmd_id' => $cmdId, // Pass Laravel's cmd_id to Python service
        ])->throw();
        return $cmdId;
    }

    public function sendNodeCommand(DeviceNode $node, array $payload): string
    {
        $cmdId = Str::uuid()->toString();
        $command = Command::create([
            'zone_id' => $node->zone_id,
            'node_id' => $node->id,
            'channel' => $payload['channel'] ?? null,
            'cmd' => $payload['type'] ?? ($payload['cmd'] ?? 'unknown'),
            'params' => $payload['params'] ?? [],
            'status' => 'pending',
            'cmd_id' => $cmdId,
        ]);
        $zoneId = $node->zone_id ?? ($payload['zone_id'] ?? null);
        $ghUid = optional(optional($node->zone)->greenhouse)->uid ?? 'gh-1';
        $baseUrl = Config::get('services.python_bridge.base_url');
        $token = Config::get('services.python_bridge.token');
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];
        // Ensure params is an associative array (dict), not a list
        // Python service expects Dict[str, Any], not a list
        // Empty array [] serializes to [] in JSON, but we need {} for Python
        $params = $command->params ?? [];
        if (is_array($params) && array_is_list($params)) {
            // Convert indexed array to empty object (will serialize as {} in JSON)
            $params = new \stdClass();
        } elseif (empty($params) && is_array($params)) {
            // Empty associative array - convert to object to ensure {} in JSON
            $params = new \stdClass();
        }
        
        Http::withHeaders($headers)->post("{$baseUrl}/bridge/nodes/{$node->uid}/commands", [
            'type' => $command->cmd,
            'params' => $params,
            'greenhouse_uid' => $ghUid,
            'zone_id' => $zoneId,
            'channel' => $payload['channel'] ?? null,
            'cmd_id' => $cmdId, // Pass Laravel's cmd_id to Python service
        ])->throw();
        return $cmdId;
    }

    /**
     * Уведомить Python-сервис об обновлении конфигурации зоны
     */
    public function notifyConfigUpdate(Zone $zone): void
    {
        $baseUrl = Config::get('services.python_bridge.base_url');
        $token = Config::get('services.python_bridge.token');
        
        if (!$baseUrl) {
            // Если URL не настроен, просто логируем
            \Illuminate\Support\Facades\Log::info('Python bridge URL not configured, skipping config update notification');
            return;
        }

        try {
            $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];
            
            // Отправляем уведомление о необходимости перезагрузить конфигурацию
            // Python-сервис должен сделать запрос к /api/system/config/full
            Http::withHeaders($headers)
                ->timeout(5)
                ->post("{$baseUrl}/bridge/config/zone-updated", [
                    'zone_id' => $zone->id,
                    'greenhouse_uid' => optional($zone->greenhouse)->uid,
                ]);
                
            \Illuminate\Support\Facades\Log::info('Python service notified about zone config update', [
                'zone_id' => $zone->id,
            ]);
        } catch (\Exception $e) {
            // Не бросаем исключение, чтобы не прерывать основной процесс
            \Illuminate\Support\Facades\Log::warning('Failed to notify Python service about zone config update', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);
        }
    }
}


