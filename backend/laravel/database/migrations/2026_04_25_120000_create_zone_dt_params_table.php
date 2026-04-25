<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('zone_dt_params', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('param_group', 32);
            $table->jsonb('params');
            $table->timestampTz('calibrated_at');
            $table->timestampTz('calibrated_from_start');
            $table->timestampTz('calibrated_from_end');
            $table->jsonb('calibration_mae')->nullable();
            $table->integer('n_samples_used')->nullable();
            $table->smallInteger('version')->default(1);
            $table->timestampTz('superseded_at')->nullable();
            $table->timestamps();

            $table->unique(['zone_id', 'param_group', 'version']);
            $table->index(['zone_id', 'param_group', 'superseded_at'], 'zone_dt_params_active_idx');
        });

        DB::statement(<<<SQL
            ALTER TABLE zone_dt_params
            ADD CONSTRAINT zone_dt_params_param_group_chk
            CHECK (param_group IN ('tank','ph','ec','climate','substrate','uptake','actuator'))
        SQL);
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_dt_params');
    }
};
