<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Таблица подтверждений команд для двухфазного подтверждения.
     * Поддерживает несколько типов подтверждений: accepted, executed, verified, error.
     */
    public function up(): void
    {
        Schema::create('command_acks', function (Blueprint $table) {
            $table->id();
            $table->foreignId('command_id')->constrained('commands')->cascadeOnDelete();
            $table->enum('ack_type', ['accepted', 'executed', 'verified', 'error'])->default('accepted');
            $table->decimal('measured_current', 10, 4)->nullable(); // Измеренный ток (для актуаторов)
            $table->decimal('measured_flow', 10, 4)->nullable(); // Измеренный поток (для насосов)
            $table->text('error_message')->nullable(); // Сообщение об ошибке (для ack_type='error')
            $table->jsonb('metadata')->nullable(); // Дополнительные данные (raw ответ, статус, и т.д.)
            $table->timestamp('created_at')->useCurrent();

            // Индексы для быстрого поиска
            $table->index(['command_id', 'ack_type'], 'command_acks_command_type_idx');
            $table->index('command_id', 'command_acks_command_idx');
            $table->index('ack_type', 'command_acks_type_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('command_acks');
    }
};

