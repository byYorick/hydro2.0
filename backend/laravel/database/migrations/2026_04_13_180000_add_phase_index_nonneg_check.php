<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::statement('ALTER TABLE recipe_revision_phases ADD CONSTRAINT recipe_revision_phases_phase_index_nonneg CHECK (phase_index >= 0)');
        DB::statement('ALTER TABLE grow_cycle_phases ADD CONSTRAINT grow_cycle_phases_phase_index_nonneg CHECK (phase_index >= 0)');
    }

    public function down(): void
    {
        DB::statement('ALTER TABLE recipe_revision_phases DROP CONSTRAINT IF EXISTS recipe_revision_phases_phase_index_nonneg');
        DB::statement('ALTER TABLE grow_cycle_phases DROP CONSTRAINT IF EXISTS grow_cycle_phases_phase_index_nonneg');
    }
};
