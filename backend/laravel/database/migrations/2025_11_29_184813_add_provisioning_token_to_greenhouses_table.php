<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Str;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('greenhouses', function (Blueprint $table) {
            $table->string('provisioning_token', 64)->nullable()->unique()->after('uid');
        });

        // Генерируем уникальные provisioning_token для существующих теплиц
        \DB::table('greenhouses')->get()->each(function ($greenhouse) {
            \DB::table('greenhouses')
                ->where('id', $greenhouse->id)
                ->update([
                    'provisioning_token' => 'gh_' . Str::random(32),
                ]);
        });

        // Делаем provisioning_token обязательным
        Schema::table('greenhouses', function (Blueprint $table) {
            $table->string('provisioning_token', 64)->nullable(false)->change();
        });
    }

    public function down(): void
    {
        Schema::table('greenhouses', function (Blueprint $table) {
            $table->dropUnique(['provisioning_token']);
            $table->dropColumn('provisioning_token');
        });
    }
};
