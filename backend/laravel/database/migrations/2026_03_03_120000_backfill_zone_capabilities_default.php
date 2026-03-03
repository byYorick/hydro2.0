<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    private const DEFAULT_CAPABILITIES = [
        'ph_control' => true,
        'ec_control' => true,
        'climate_control' => true,
        'light_control' => true,
        'irrigation_control' => true,
        'recirculation' => true,
        'flow_sensor' => true,
    ];

    public function up(): void
    {
        $default = json_encode(self::DEFAULT_CAPABILITIES);

        // Выставляем дефолт на уровне колонки
        DB::statement("ALTER TABLE zones ALTER COLUMN capabilities SET DEFAULT '{$default}'::jsonb");

        // Заполняем уже существующие зоны с NULL capabilities
        DB::statement("UPDATE zones SET capabilities = '{$default}'::jsonb WHERE capabilities IS NULL");
    }

    public function down(): void
    {
        DB::statement('ALTER TABLE zones ALTER COLUMN capabilities DROP DEFAULT');
    }
};
