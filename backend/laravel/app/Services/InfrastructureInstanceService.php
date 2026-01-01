<?php

namespace App\Services;

use App\Models\Greenhouse;
use App\Models\InfrastructureInstance;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Collection;

class InfrastructureInstanceService
{
    /**
     * Создать экземпляр инфраструктуры
     */
    public function create(array $data): InfrastructureInstance
    {
        return InfrastructureInstance::create($data);
    }

    /**
     * Обновить экземпляр инфраструктуры
     */
    public function update(InfrastructureInstance $instance, array $data): InfrastructureInstance
    {
        $instance->update($data);

        return $instance->fresh()->load('channelBindings');
    }

    /**
     * Удалить экземпляр инфраструктуры
     */
    public function delete(InfrastructureInstance $instance): void
    {
        $instance->delete();
    }

    /**
     * Получить все экземпляры инфраструктуры для зоны
     */
    public function getForZone(Zone $zone): Collection
    {
        return InfrastructureInstance::where('owner_type', 'zone')
            ->where('owner_id', $zone->id)
            ->with('channelBindings.nodeChannel.node')
            ->get();
    }

    /**
     * Получить все экземпляры инфраструктуры для теплицы
     */
    public function getForGreenhouse(Greenhouse $greenhouse): Collection
    {
        return InfrastructureInstance::where('owner_type', 'greenhouse')
            ->where('owner_id', $greenhouse->id)
            ->with('channelBindings.nodeChannel.node')
            ->get();
    }
}
