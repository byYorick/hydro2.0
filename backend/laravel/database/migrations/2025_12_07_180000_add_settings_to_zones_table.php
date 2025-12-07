<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('zones')) {
            return;
        }

        Schema::table('zones', function (Blueprint $table) {
            if (! Schema::hasColumn('zones', 'settings')) {
                // Используем jsonb, так как проект работает на Postgres
                $table->jsonb('settings')->nullable()->after('solution_started_at');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('zones')) {
            return;
        }

        Schema::table('zones', function (Blueprint $table) {
            if (Schema::hasColumn('zones', 'settings')) {
                $table->dropColumn('settings');
            }
        });
    }
};
