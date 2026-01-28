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
     * Обновляет статусы команд согласно единому контракту:
     * QUEUED/SENT/ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED
     */
    public function up(): void
    {
        // Проверяем, существует ли таблица commands
        if (!Schema::hasTable('commands')) {
            return; // Таблица будет создана в другой миграции
        }
        
        // Сначала обновляем существующие данные для миграции старых статусов
        DB::statement("
            UPDATE commands 
            SET status = CASE 
                WHEN status = 'pending' THEN 'QUEUED'
                WHEN status = 'sent' THEN 'SENT'
                WHEN status = 'ack' THEN 'ACK'
                WHEN status = 'accepted' THEN 'ACK'
                WHEN status = 'done' THEN 'DONE'
                WHEN status = 'completed' THEN 'DONE'
                WHEN status = 'failed' THEN 'ERROR'
                WHEN status = 'timeout' THEN 'TIMEOUT'
                WHEN status = 'send_failed' THEN 'SEND_FAILED'
                ELSE 'QUEUED'
            END
        ");

        // Обновляем колонку status для поддержки новых значений
        // В PostgreSQL мы используем CHECK constraint вместо ENUM для гибкости
        Schema::table('commands', function (Blueprint $table) {
            // Удаляем старый индекс если есть
            $table->dropIndex('commands_status_idx');
        });

        // Добавляем CHECK constraint для валидации статусов
        DB::statement("
            ALTER TABLE commands 
            ADD CONSTRAINT commands_status_check 
            CHECK (status IN ('QUEUED', 'SENT', 'ACK', 'DONE', 'NO_EFFECT', 'ERROR', 'INVALID', 'BUSY', 'TIMEOUT', 'SEND_FAILED'))
        ");

        // Восстанавливаем индекс
        Schema::table('commands', function (Blueprint $table) {
            $table->index('status', 'commands_status_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Проверяем, существует ли таблица commands
        if (!Schema::hasTable('commands')) {
            return; // Таблица не существует, нечего откатывать
        }
        
        // Удаляем CHECK constraint
        DB::statement('ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_status_check');

        // Возвращаем старые статусы
        DB::statement("
            UPDATE commands 
            SET status = CASE 
                WHEN status = 'QUEUED' THEN 'pending'
                WHEN status = 'SENT' THEN 'sent'
                WHEN status = 'ACK' THEN 'ack'
                WHEN status = 'DONE' THEN 'ack'
                WHEN status = 'NO_EFFECT' THEN 'ack'
                WHEN status = 'ERROR' THEN 'failed'
                WHEN status = 'INVALID' THEN 'failed'
                WHEN status = 'BUSY' THEN 'failed'
                WHEN status = 'TIMEOUT' THEN 'timeout'
                WHEN status = 'SEND_FAILED' THEN 'failed'
                ELSE 'pending'
            END
        ");
    }
};
