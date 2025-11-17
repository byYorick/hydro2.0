<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->decimal('health_score', 5, 2)->nullable()->after('status')->comment('Health score 0-100');
            $table->string('health_status', 16)->nullable()->after('health_score')->comment('ok/warning/alarm');
        });
    }

    public function down(): void
    {
        Schema::table('zones', function (Blueprint $table) {
            $table->dropColumn(['health_score', 'health_status']);
        });
    }
};

