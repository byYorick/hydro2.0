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
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete();
            $table->string('channel')->nullable();
            $table->string('metric_type');
            $table->float('value')->nullable();
            $table->jsonb('raw')->nullable();
            $table->timestamp('ts')->index();
            $table->timestamp('created_at')->useCurrent();
            $table->index(['zone_id', 'metric_type', 'ts'], 'telemetry_samples_zone_metric_ts_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('telemetry_samples');
    }
};


