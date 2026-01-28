<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('telemetry_samples', function (Blueprint $table) {
            $table->id();
            $table->unsignedBigInteger('sensor_id');
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->unsignedBigInteger('cycle_id')->nullable();
            $table->decimal('value', 10, 4);
            $table->enum('quality', ['GOOD', 'BAD', 'UNCERTAIN'])->default('GOOD');
            $table->jsonb('metadata')->nullable();
            $table->timestamp('ts');
            $table->timestamp('created_at')->useCurrent();

            $table->index(['sensor_id', 'ts'], 'telemetry_samples_sensor_ts_idx');
            $table->index(['zone_id', 'ts'], 'telemetry_samples_zone_ts_idx');
            $table->index(['cycle_id', 'ts'], 'telemetry_samples_cycle_ts_idx');
            $table->index('ts', 'telemetry_samples_ts_idx');
            $table->index('quality', 'telemetry_samples_quality_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('telemetry_samples');
    }
};
