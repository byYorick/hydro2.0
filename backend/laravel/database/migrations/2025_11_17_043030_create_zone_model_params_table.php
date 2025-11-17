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
        Schema::create('zone_model_params', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('model_type', 32); // ph, ec, climate
            $table->jsonb('params'); // параметры модели (буферная ёмкость, коэффициенты и т.д.)
            $table->timestamp('calibrated_at')->nullable();
            $table->timestamps();
            
            $table->unique(['zone_id', 'model_type']);
            $table->index('zone_id');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('zone_model_params');
    }
};
