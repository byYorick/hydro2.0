<?php

namespace App\Services;

use App\Models\ChannelBinding;

class ChannelBindingService
{
    /**
     * Создать привязку канала
     */
    public function create(array $data): ChannelBinding
    {
        return ChannelBinding::create($data);
    }

    /**
     * Обновить привязку канала
     */
    public function update(ChannelBinding $binding, array $data): ChannelBinding
    {
        $binding->update($data);

        return $binding->fresh()->load('infrastructureInstance', 'node');
    }

    /**
     * Удалить привязку канала
     */
    public function delete(ChannelBinding $binding): void
    {
        $binding->delete();
    }
}

