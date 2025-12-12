<?php

namespace App\Services;

use App\Models\Zone;
use App\Models\ZoneInfrastructure;
use App\Models\ZoneChannelBinding;
use App\Models\DeviceNode;
use Carbon\Carbon;
use Illuminate\Support\Collection;

class ZoneReadinessService
{
    /**
     * Валидация готовности зоны к старту цикла
     * 
     * @param int $zoneId
     * @return array{valid: bool, errors: array, warnings: array}
     */
    public function validate(int $zoneId): array
    {
        $zone = Zone::with(['infrastructure.channelBindings.node'])->findOrFail($zoneId);
        
        $errors = [];
        $warnings = [];
        
        // 1. Проверка наличия required assets
        $requiredAssets = $zone->infrastructure
            ->where('required', true);
        
        if ($requiredAssets->isEmpty()) {
            $errors[] = [
                'code' => 'NO_REQUIRED_ASSETS',
                'message' => 'В зоне не настроено обязательное оборудование',
            ];
        }
        
        // 2. Проверка привязок для каждого required asset
        foreach ($requiredAssets as $asset) {
            $bindings = $asset->channelBindings;
            
            if ($bindings->isEmpty()) {
                $errors[] = [
                    'code' => 'ASSET_NOT_BOUND',
                    'message' => "Оборудование '{$asset->label}' ({$asset->asset_type}) не привязано к каналам",
                    'asset_id' => $asset->id,
                    'asset_type' => $asset->asset_type,
                    'asset_label' => $asset->label,
                ];
                continue;
            }
            
            // 3. Проверка онлайн-статуса нод для каждого binding (soft requirement - warning)
            foreach ($bindings as $binding) {
                $node = $binding->node;
                
                if (!$node) {
                    $errors[] = [
                        'code' => 'BINDING_NODE_NOT_FOUND',
                        'message' => "Нода не найдена для привязки оборудования '{$asset->label}'",
                        'asset_id' => $asset->id,
                        'binding_id' => $binding->id,
                    ];
                    continue;
                }
                
                // Проверка онлайн-статуса (soft requirement)
                if (!$this->isNodeOnline($node)) {
                    $warnings[] = [
                        'code' => 'NODE_OFFLINE',
                        'message' => "Нода '{$node->name}' ({$node->uid}) для оборудования '{$asset->label}' находится offline",
                        'asset_id' => $asset->id,
                        'asset_label' => $asset->label,
                        'node_id' => $node->id,
                        'node_uid' => $node->uid,
                        'node_name' => $node->name,
                        'node_status' => $node->status,
                        'last_heartbeat_at' => $node->last_heartbeat_at?->toIso8601String(),
                    ];
                }
            }
        }
        
        return [
            'valid' => empty($errors),
            'errors' => $errors,
            'warnings' => $warnings,
        ];
    }
    
    /**
     * Проверить, является ли нода онлайн
     * 
     * @param DeviceNode $node
     * @return bool
     */
    private function isNodeOnline(DeviceNode $node): bool
    {
        // Проверяем статус
        if ($node->status !== 'online') {
            return false;
        }
        
        // Проверяем последний heartbeat (если есть)
        // Считаем ноду офлайн, если последний heartbeat был более 5 минут назад
        if ($node->last_heartbeat_at) {
            $heartbeatAge = Carbon::now()->diffInMinutes($node->last_heartbeat_at);
            if ($heartbeatAge > 5) {
                return false;
            }
        } else {
            // Если нет heartbeat, проверяем last_seen_at
            if ($node->last_seen_at) {
                $seenAge = Carbon::now()->diffInMinutes($node->last_seen_at);
                if ($seenAge > 5) {
                    return false;
                }
            } else {
                // Если нет ни heartbeat, ни last_seen_at, считаем офлайн
                return false;
            }
        }
        
        return true;
    }
}

