<?php

namespace App\Services;

use App\Models\Preset;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class PresetService
{
    /**
     * Создать пресет
     */
    public function create(array $data): Preset
    {
        return DB::transaction(function () use ($data) {
            $preset = Preset::create($data);
            Log::info('Preset created', ['preset_id' => $preset->id, 'name' => $preset->name]);
            return $preset;
        });
    }

    /**
     * Обновить пресет
     */
    public function update(Preset $preset, array $data): Preset
    {
        return DB::transaction(function () use ($preset, $data) {
            $preset->update($data);
            Log::info('Preset updated', ['preset_id' => $preset->id]);
            return $preset->fresh();
        });
    }

    /**
     * Удалить пресет (с проверкой инвариантов)
     */
    public function delete(Preset $preset): void
    {
        DB::transaction(function () use ($preset) {
            // Проверка: нельзя удалить пресет, который используется в зонах
            $activeZones = \App\Models\Zone::where('preset_id', $preset->id)->count();
            if ($activeZones > 0) {
                throw new \DomainException("Cannot delete preset that is used in {$activeZones} zone(s). Please detach from zones first.");
            }

            $presetId = $preset->id;
            $presetName = $preset->name;
            $preset->delete();
            Log::info('Preset deleted', ['preset_id' => $presetId, 'name' => $presetName]);
        });
    }
}

