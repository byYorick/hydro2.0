<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Кэш последних значений сенсоров для быстрого доступа.
     * Обновляется триггерами или отдельным job'ом.
     * 
     * ВНИМАНИЕ: Заменяет старую структуру telemetry_last (zone_id, node_id, metric_type)
     * на новую структуру с sensor_id.
     */
    public function up(): void
    {
        // Удаляем старую таблицу, если она существует (без обратной совместимости)
        Schema::dropIfExists('telemetry_last');
        
        Schema::create('telemetry_last', function (Blueprint $table) {
            $table->foreignId('sensor_id')->primary()->constrained('sensors')->cascadeOnDelete();
            $table->decimal('last_value', 10, 4); // Последнее значение
            $table->timestamp('last_ts'); // Время последнего измерения
            $table->enum('last_quality', ['GOOD', 'BAD', 'UNCERTAIN'])->default('GOOD');
            $table->timestamp('updated_at')->useCurrent()->useCurrentOnUpdate();

            // Индекс для быстрого поиска по времени
            $table->index('last_ts', 'telemetry_last_ts_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('telemetry_last');
    }
};

