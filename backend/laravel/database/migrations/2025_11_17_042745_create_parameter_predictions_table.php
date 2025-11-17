<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('parameter_predictions', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('metric_type', 64); // ph, ec, temp_air, humidity_air
            $table->float('predicted_value');
            $table->float('confidence')->nullable(); // 0.0-1.0
            $table->integer('horizon_minutes'); // горизонт прогноза в минутах
            $table->timestamp('predicted_at'); // время, на которое сделан прогноз
            $table->timestamps();
            
            $table->index(['zone_id', 'metric_type', 'predicted_at']);
            $table->index(['zone_id', 'created_at']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('parameter_predictions');
    }
};
