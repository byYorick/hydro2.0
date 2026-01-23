<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (!Schema::hasTable('grow_cycle_transitions')) {
            return;
        }

        Schema::table('grow_cycle_transitions', function (Blueprint $table) {
            $table->dropForeign(['from_phase_id']);
            $table->dropForeign(['to_phase_id']);
            $table->dropForeign(['from_step_id']);
            $table->dropForeign(['to_step_id']);

            $table->foreign('from_phase_id')->references('id')->on('recipe_revision_phases')->nullOnDelete();
            $table->foreign('to_phase_id')->references('id')->on('recipe_revision_phases')->nullOnDelete();
            $table->foreign('from_step_id')->references('id')->on('recipe_revision_phase_steps')->nullOnDelete();
            $table->foreign('to_step_id')->references('id')->on('recipe_revision_phase_steps')->nullOnDelete();
        });
    }

    public function down(): void
    {
        if (!Schema::hasTable('grow_cycle_transitions')) {
            return;
        }

        Schema::table('grow_cycle_transitions', function (Blueprint $table) {
            $table->dropForeign(['from_phase_id']);
            $table->dropForeign(['to_phase_id']);
            $table->dropForeign(['from_step_id']);
            $table->dropForeign(['to_step_id']);

            $table->foreign('from_phase_id')->references('id')->on('recipe_revision_phases')->restrictOnDelete();
            $table->foreign('to_phase_id')->references('id')->on('recipe_revision_phases')->restrictOnDelete();
            $table->foreign('from_step_id')->references('id')->on('recipe_revision_phase_steps')->restrictOnDelete();
            $table->foreign('to_step_id')->references('id')->on('recipe_revision_phase_steps')->restrictOnDelete();
        });
    }
};
