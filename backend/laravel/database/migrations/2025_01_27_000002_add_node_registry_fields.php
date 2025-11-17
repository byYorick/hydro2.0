<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        // Проверяем, существует ли таблица
        if (!Schema::hasTable('nodes')) {
            return; // Таблица создается в другой миграции
        }

        Schema::table('nodes', function (Blueprint $table) {
            if (!Schema::hasColumn('nodes', 'validated')) {
                $table->boolean('validated')->default(false)->after('status');
            }
            if (!Schema::hasColumn('nodes', 'first_seen_at')) {
                $table->timestamp('first_seen_at')->nullable()->after('validated');
            }
            if (!Schema::hasColumn('nodes', 'hardware_revision')) {
                $table->string('hardware_revision')->nullable()->after('fw_version');
            }
        });
    }

    public function down(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            $table->dropColumn(['validated', 'first_seen_at', 'hardware_revision']);
        });
    }
};

