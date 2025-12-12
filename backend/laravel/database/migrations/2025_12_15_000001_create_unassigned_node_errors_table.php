<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('unassigned_node_errors', function (Blueprint $table) {
            $table->id();
            $table->string('hardware_id')->index(); // hardware_id из temp-топика
            $table->text('error_message'); // Текст ошибки
            $table->string('error_code')->nullable(); // Код ошибки
            $table->string('error_level')->default('ERROR'); // Уровень ошибки (ERROR, WARNING, etc)
            $table->string('topic'); // MQTT топик, откуда пришла ошибка
            $table->jsonb('error_data')->nullable(); // Дополнительные данные ошибки
            $table->integer('count')->default(1); // Количество повторений
            $table->timestamp('first_seen_at'); // Когда впервые увидели
            $table->timestamp('last_seen_at'); // Когда последний раз видели
            $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete(); // Привязывается при регистрации
            $table->timestamps();
            
            // Уникальный индекс для upsert: hardware_id + COALESCE(error_code, '') + topic
            // Используем выражение для обработки NULL в error_code
            $table->unique(['hardware_id', 'topic'], 'unassigned_errors_hardware_topic_unique');
            
            // Индексы для быстрого поиска
            $table->index('hardware_id', 'unassigned_errors_hardware_id_idx');
            $table->index('node_id', 'unassigned_errors_node_id_idx');
            $table->index('last_seen_at', 'unassigned_errors_last_seen_idx');
            $table->index(['hardware_id', 'error_code'], 'unassigned_errors_hardware_error_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('unassigned_node_errors');
    }
};
