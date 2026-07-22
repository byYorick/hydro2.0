<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (Schema::hasTable('zone_prepare_baselines')) {
            return;
        }

        Schema::create('zone_prepare_baselines', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->foreignId('grow_cycle_id')->nullable()->constrained('grow_cycles')->nullOnDelete();
            $table->unsignedBigInteger('ae_task_id')->nullable();
            $table->decimal('water_ec', 10, 4)->nullable();
            $table->decimal('water_ph', 10, 4)->nullable();
            $table->decimal('target_ec', 10, 4)->nullable();
            $table->decimal('nutrient_ec_budget', 10, 4)->nullable();
            $table->jsonb('ratios_json')->nullable();
            $table->jsonb('component_targets_json')->nullable();
            $table->timestampTz('captured_at');
            $table->string('source', 64)->default('ae3');
            $table->timestamps();

            $table->index('grow_cycle_id', 'zone_prepare_baselines_grow_cycle_id_idx');
        });

        if (Schema::hasTable('ae_tasks')) {
            Schema::table('zone_prepare_baselines', function (Blueprint $table): void {
                $table->foreign('ae_task_id')
                    ->references('id')
                    ->on('ae_tasks')
                    ->nullOnDelete();
            });
        }

        // DESC index for latest-baseline lookups: (zone_id, captured_at DESC).
        DB::statement(
            'CREATE INDEX zone_prepare_baselines_zone_captured_at_desc_idx
             ON zone_prepare_baselines (zone_id, captured_at DESC)'
        );
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_prepare_baselines');
    }
};
