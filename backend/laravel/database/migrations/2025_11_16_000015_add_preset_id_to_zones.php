<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->foreignId('preset_id')->nullable()->after('greenhouse_id')->constrained('presets')->nullOnDelete();
        });
    }

    public function down(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->dropForeign(['preset_id']);
            $table->dropColumn('preset_id');
        });
    }
};

