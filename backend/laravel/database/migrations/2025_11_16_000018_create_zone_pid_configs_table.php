<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('zone_pid_configs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('type', 10); // 'ph' | 'ec'
            $table->jsonb('config'); // PID параметры
            $table->timestamp('updated_at')->useCurrent();
            $table->foreignId('updated_by')->nullable()->constrained('users')->nullOnDelete();

            // Уникальный индекс: одна конфигурация PID на зону и тип
            $table->unique(['zone_id', 'type'], 'zone_pid_configs_zone_id_type_unique');

            // Индексы для быстрого поиска
            $table->index('zone_id', 'zone_pid_configs_zone_id_idx');
            $table->index('type', 'zone_pid_configs_type_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_pid_configs');
    }
};
