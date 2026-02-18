<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('zone_workflow_state', function (Blueprint $table) {
            $table->foreignId('zone_id')->primary()->constrained('zones')->cascadeOnDelete();
            $table->string('workflow_phase', 50)->default('idle');
            $table->timestampTz('started_at')->nullable();
            $table->timestampTz('updated_at')->useCurrent();
            $table->jsonb('payload')->default(DB::raw("'{}'::jsonb"));
            $table->string('scheduler_task_id', 100)->nullable();

            $table->index('workflow_phase');
            $table->index('updated_at');
            $table->index('scheduler_task_id');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('zone_workflow_state');
    }
};
