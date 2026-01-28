<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('simulation_reports')) {
            Schema::create('simulation_reports', function (Blueprint $table) {
                $table->id();
                $table->foreignId('simulation_id')->constrained('zone_simulations')->cascadeOnDelete();
                $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
                $table->string('status', 32)->default('running');
                $table->timestamp('started_at')->nullable();
                $table->timestamp('finished_at')->nullable();
                $table->jsonb('summary_json')->nullable();
                $table->jsonb('phases_json')->nullable();
                $table->jsonb('metrics_json')->nullable();
                $table->jsonb('errors_json')->nullable();
                $table->timestamps();

                $table->unique('simulation_id');
                $table->index('zone_id');
                $table->index('status');
            });

            return;
        }

        Schema::table('simulation_reports', function (Blueprint $table) {
            if (! Schema::hasColumn('simulation_reports', 'simulation_id')) {
                $table->foreignId('simulation_id')->constrained('zone_simulations')->cascadeOnDelete();
            }
            if (! Schema::hasColumn('simulation_reports', 'zone_id')) {
                $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            }
            if (! Schema::hasColumn('simulation_reports', 'status')) {
                $table->string('status', 32)->default('running');
            }
            if (! Schema::hasColumn('simulation_reports', 'started_at')) {
                $table->timestamp('started_at')->nullable();
            }
            if (! Schema::hasColumn('simulation_reports', 'finished_at')) {
                $table->timestamp('finished_at')->nullable();
            }
            if (! Schema::hasColumn('simulation_reports', 'summary_json')) {
                $table->jsonb('summary_json')->nullable();
            }
            if (! Schema::hasColumn('simulation_reports', 'phases_json')) {
                $table->jsonb('phases_json')->nullable();
            }
            if (! Schema::hasColumn('simulation_reports', 'metrics_json')) {
                $table->jsonb('metrics_json')->nullable();
            }
            if (! Schema::hasColumn('simulation_reports', 'errors_json')) {
                $table->jsonb('errors_json')->nullable();
            }
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('simulation_reports');
    }
};
