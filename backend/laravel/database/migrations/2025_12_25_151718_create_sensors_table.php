<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Единая таблица сенсоров для зон, теплиц и наружных датчиков.
     * zone_id nullable для тепличных/наружных датчиков.
     */
    public function up(): void
    {
        Schema::create('sensors', function (Blueprint $table) {
            $table->id();
            $table->foreignId('greenhouse_id')->constrained('greenhouses')->cascadeOnDelete();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete(); // NULL для тепличных/наружных
            $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete(); // Если датчик физически на ноде
            $table->enum('scope', ['inside', 'outside'])->default('inside'); // Внутри или снаружи
            $table->enum('type', [
                'TEMPERATURE',
                'HUMIDITY',
                'CO2',
                'PH',
                'EC',
                'WATER_LEVEL',
                'WIND_SPEED',
                'WIND_DIRECTION',
                'PRESSURE',
                'LIGHT_INTENSITY',
                'SOIL_MOISTURE',
                'OTHER'
            ])->default('TEMPERATURE');
            $table->string('label'); // Человекочитаемое название
            $table->string('unit')->nullable(); // Единица измерения (C, %, ppm, и т.д.)
            $table->jsonb('specs')->nullable(); // Дополнительные характеристики (точность, диапазон, и т.д.)
            $table->boolean('is_active')->default(true);
            $table->timestamp('last_read_at')->nullable(); // Последнее чтение значения
            $table->timestamps();

            // Индексы для быстрого поиска
            $table->index('zone_id', 'sensors_zone_idx');
            $table->index(['greenhouse_id', 'scope'], 'sensors_greenhouse_scope_idx');
            $table->index(['greenhouse_id', 'type'], 'sensors_greenhouse_type_idx');
            $table->index('node_id', 'sensors_node_idx');
            $table->index('is_active', 'sensors_active_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('sensors');
    }
};

