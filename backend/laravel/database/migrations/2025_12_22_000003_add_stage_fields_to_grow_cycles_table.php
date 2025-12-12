<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('grow_cycles', function (Blueprint $table) {
            $table->string('current_stage_code', 64)->nullable()->after('status');
            $table->timestamp('current_stage_started_at')->nullable()->after('current_stage_code');
            $table->timestamp('planting_at')->nullable()->after('started_at'); // Дата посадки
            // expected_harvest_at уже существует, но убедимся что он есть
            if (!Schema::hasColumn('grow_cycles', 'expected_harvest_at')) {
                $table->timestamp('expected_harvest_at')->nullable()->after('recipe_started_at');
            }

            $table->index('current_stage_code', 'grow_cycles_current_stage_code_idx');
        });
    }

    public function down(): void
    {
        Schema::table('grow_cycles', function (Blueprint $table) {
            $table->dropIndex('grow_cycles_current_stage_code_idx');
            $table->dropColumn(['current_stage_code', 'current_stage_started_at', 'planting_at']);
        });
    }
};

