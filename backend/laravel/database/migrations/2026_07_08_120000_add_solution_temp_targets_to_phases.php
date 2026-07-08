<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        foreach (['recipe_revision_phases', 'grow_cycle_phases'] as $tableName) {
            Schema::table($tableName, function (Blueprint $table): void {
                $table->decimal('solution_temp_target', 5, 2)->nullable()->after('co2_target');
                $table->decimal('solution_temp_min', 5, 2)->nullable()->after('solution_temp_target');
                $table->decimal('solution_temp_max', 5, 2)->nullable()->after('solution_temp_min');
            });
        }
    }

    public function down(): void
    {
        foreach (['recipe_revision_phases', 'grow_cycle_phases'] as $tableName) {
            Schema::table($tableName, function (Blueprint $table): void {
                $table->dropColumn([
                    'solution_temp_target',
                    'solution_temp_min',
                    'solution_temp_max',
                ]);
            });
        }
    }
};
