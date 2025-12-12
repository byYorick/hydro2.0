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
     * QUEUED/SENT/ACCEPTED/DONE/FAILED/TIMEOUT/SEND_FAILED
     */
    public function up(): void
    {
        // Сначала обновляем существующие данные для миграции старых статусов
        DB::statement("
            UPDATE commands 
            SET status = CASE 
                WHEN status = 'pending' THEN 'QUEUED'
                WHEN status = 'sent' THEN 'SENT'
                WHEN status = 'ack' THEN 'DONE'
                WHEN status = 'failed' THEN 'FAILED'
                WHEN status = 'timeout' THEN 'TIMEOUT'
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
            CHECK (status IN ('QUEUED', 'SENT', 'ACCEPTED', 'DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED'))
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
        // Удаляем CHECK constraint
        DB::statement('ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_status_check');

        // Возвращаем старые статусы
        DB::statement("
            UPDATE commands 
            SET status = CASE 
                WHEN status = 'QUEUED' THEN 'pending'
                WHEN status = 'SENT' THEN 'sent'
                WHEN status = 'ACCEPTED' THEN 'sent'
                WHEN status = 'DONE' THEN 'ack'
                WHEN status = 'FAILED' THEN 'failed'
                WHEN status = 'TIMEOUT' THEN 'timeout'
                WHEN status = 'SEND_FAILED' THEN 'failed'
                ELSE 'pending'
            END
        ");
    }
};
