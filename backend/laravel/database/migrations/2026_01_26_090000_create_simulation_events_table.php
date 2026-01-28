<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('simulation_events')) {
            Schema::create('simulation_events', function (Blueprint $table) {
                $table->id();
                $table->foreignId('simulation_id')->constrained('zone_simulations')->cascadeOnDelete();
                $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
                $table->string('service', 64);
                $table->string('stage', 64);
                $table->string('status', 32);
                $table->string('level', 16)->default('info');
                $table->text('message')->nullable();
                $table->jsonb('payload')->nullable();
                $table->timestamp('occurred_at')->useCurrent();
                $table->timestamp('created_at')->useCurrent();

                $table->index(['simulation_id', 'occurred_at'], 'simulation_events_sim_id_occurred_idx');
                $table->index(['zone_id', 'occurred_at'], 'simulation_events_zone_id_occurred_idx');
                $table->index(['service', 'stage'], 'simulation_events_service_stage_idx');
                $table->index('status', 'simulation_events_status_idx');
            });

            return;
        }

        Schema::table('simulation_events', function (Blueprint $table) {
            if (! Schema::hasColumn('simulation_events', 'simulation_id')) {
                $table->foreignId('simulation_id')->constrained('zone_simulations')->cascadeOnDelete();
            }
            if (! Schema::hasColumn('simulation_events', 'zone_id')) {
                $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            }
            if (! Schema::hasColumn('simulation_events', 'service')) {
                $table->string('service', 64)->default('unknown');
            }
            if (! Schema::hasColumn('simulation_events', 'stage')) {
                $table->string('stage', 64)->default('unknown');
            }
            if (! Schema::hasColumn('simulation_events', 'status')) {
                $table->string('status', 32)->default('unknown');
            }
            if (! Schema::hasColumn('simulation_events', 'level')) {
                $table->string('level', 16)->default('info');
            }
            if (! Schema::hasColumn('simulation_events', 'message')) {
                $table->text('message')->nullable();
            }
            if (! Schema::hasColumn('simulation_events', 'payload')) {
                $table->jsonb('payload')->nullable();
            }
            if (! Schema::hasColumn('simulation_events', 'occurred_at')) {
                $table->timestamp('occurred_at')->useCurrent();
            }
            if (! Schema::hasColumn('simulation_events', 'created_at')) {
                $table->timestamp('created_at')->useCurrent();
            }
        });

        DB::statement('CREATE INDEX IF NOT EXISTS simulation_events_sim_id_occurred_idx ON simulation_events (simulation_id, occurred_at)');
        DB::statement('CREATE INDEX IF NOT EXISTS simulation_events_zone_id_occurred_idx ON simulation_events (zone_id, occurred_at)');
        DB::statement('CREATE INDEX IF NOT EXISTS simulation_events_service_stage_idx ON simulation_events (service, stage)');
        DB::statement('CREATE INDEX IF NOT EXISTS simulation_events_status_idx ON simulation_events (status)');
    }

    public function down(): void
    {
        Schema::dropIfExists('simulation_events');
    }
};
