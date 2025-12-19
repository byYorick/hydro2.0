<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Добавляет поля ответа команд, если они отсутствуют.
     */
    public function up(): void
    {
        if (! Schema::hasTable('commands')) {
            return;
        }

        Schema::table('commands', function (Blueprint $table) {
            if (! Schema::hasColumn('commands', 'error_code')) {
                $table->string('error_code', 64)->nullable()->after('failed_at');
            }
            if (! Schema::hasColumn('commands', 'error_message')) {
                $table->string('error_message', 512)->nullable()->after('error_code');
            }
            if (! Schema::hasColumn('commands', 'result_code')) {
                $table->integer('result_code')->default(0)->after('error_message');
            }
            if (! Schema::hasColumn('commands', 'duration_ms')) {
                $table->integer('duration_ms')->nullable()->after('result_code');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('commands')) {
            return;
        }

        Schema::table('commands', function (Blueprint $table) {
            $columns = [];
            if (Schema::hasColumn('commands', 'duration_ms')) {
                $columns[] = 'duration_ms';
            }
            if (Schema::hasColumn('commands', 'result_code')) {
                $columns[] = 'result_code';
            }
            if (Schema::hasColumn('commands', 'error_message')) {
                $columns[] = 'error_message';
            }
            if (Schema::hasColumn('commands', 'error_code')) {
                $columns[] = 'error_code';
            }

            if ($columns) {
                $table->dropColumn($columns);
            }
        });
    }
};
