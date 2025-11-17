<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->jsonb('hardware_profile')->nullable()->after('description');
            $table->jsonb('capabilities')->nullable()->after('hardware_profile');
        });
    }

    public function down(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->dropColumn(['hardware_profile', 'capabilities']);
        });
    }
};

