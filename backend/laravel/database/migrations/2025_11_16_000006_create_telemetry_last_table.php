<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('telemetry_last', function (Blueprint $table) {
            $table->unsignedBigInteger('zone_id');
            $table->string('metric_type');
            $table->unsignedBigInteger('node_id')->nullable();
            $table->string('channel')->nullable();
            $table->float('value')->nullable();
            $table->timestamp('updated_at')->nullable();

            $table->primary(['zone_id', 'metric_type']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('telemetry_last');
    }
};


