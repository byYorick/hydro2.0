<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Добавляет поля для единого контракта CommandResponse:
     * - error_code: символический код ошибки
     * - error_message: сообщение об ошибке
     * - result_code: код результата выполнения (0 = успех)
     * - duration_ms: длительность выполнения в миллисекундах
     */
    public function up(): void
    {
        // Проверяем, существует ли таблица commands
        if (!Schema::hasTable('commands')) {
            return; // Таблица будет создана в другой миграции
        }
        Schema::table('commands', function (Blueprint $table) {
            $table->string('error_code', 64)->nullable()->after('failed_at');
            $table->string('error_message', 512)->nullable()->after('error_code');
            $table->integer('result_code')->default(0)->after('error_message');
            $table->integer('duration_ms')->nullable()->after('result_code');
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
        
        Schema::table('commands', function (Blueprint $table) {
            $table->dropColumn(['error_code', 'error_message', 'result_code', 'duration_ms']);
        });
    }
};
