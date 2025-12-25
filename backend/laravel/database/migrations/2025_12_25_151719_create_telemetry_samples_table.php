<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Таблица телеметрии с партиционированием по месяцам.
     * zone_id и cycle_id проставляются сервером для удобства запросов.
     */
    public function up(): void
    {
        // Создаём основную таблицу без партиционирования (для совместимости с Laravel)
        // Партиционирование будет настроено отдельным SQL скриптом
        Schema::create('telemetry_samples', function (Blueprint $table) {
            $table->id();
            $table->foreignId('sensor_id')->constrained('sensors')->cascadeOnDelete();
            $table->timestamp('ts'); // Время измерения
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete(); // Проставляется сервером
            $table->foreignId('cycle_id')->nullable()->constrained('grow_cycles')->nullOnDelete(); // Проставляется сервером
            $table->decimal('value', 10, 4); // Значение измерения
            $table->enum('quality', ['GOOD', 'BAD', 'UNCERTAIN'])->default('GOOD');
            $table->jsonb('metadata')->nullable(); // Дополнительные данные (raw значение, статус, и т.д.)
            $table->timestamp('created_at')->useCurrent();

            // Индексы для быстрого поиска
            $table->index(['sensor_id', 'ts'], 'telemetry_samples_sensor_ts_idx');
            $table->index(['zone_id', 'ts'], 'telemetry_samples_zone_ts_idx');
            $table->index(['cycle_id', 'ts'], 'telemetry_samples_cycle_ts_idx');
            $table->index('ts', 'telemetry_samples_ts_idx'); // Для партиционирования
            $table->index('quality', 'telemetry_samples_quality_idx');
        });

        // Создаём функцию для партиционирования (будет выполнена отдельным SQL скриптом)
        // Партиционирование по месяцам будет настроено через pg_partman или вручную
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('telemetry_samples');
    }
};

