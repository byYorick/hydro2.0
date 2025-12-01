<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->string('uid', 64)->nullable()->after('id');
        });

        // Генерируем uid для существующих зон на основе id
        DB::statement("UPDATE zones SET uid = 'zn-' || id WHERE uid IS NULL");

        // Делаем uid уникальным и обязательным
        Schema::table('zones', function (Blueprint $table) {
            $table->string('uid', 64)->unique()->change();
        });
    }

    public function down(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->dropUnique(['uid']);
            $table->dropColumn('uid');
        });
    }
};
