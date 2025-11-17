<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('presets', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->string('plant_type'); // lettuce, arugula, tomato, microgreens, basil, strawberry, etc.
            $table->jsonb('ph_optimal_range')->nullable(); // {min: 5.5, max: 6.5}
            $table->jsonb('ec_range')->nullable(); // {min: 1.0, max: 2.0}
            $table->jsonb('vpd_range')->nullable(); // {min: 0.8, max: 1.2}
            $table->jsonb('light_intensity_range')->nullable(); // {min: 200, max: 600}
            $table->jsonb('climate_ranges')->nullable(); // {temp_day: {min: 22, max: 26}, temp_night: {...}, humidity_day: {...}}
            $table->jsonb('irrigation_behavior')->nullable(); // {interval_sec: 900, duration_sec: 8, adaptive: true}
            $table->string('growth_profile')->default('mid'); // fast/mid/slow
            $table->foreignId('default_recipe_id')->nullable()->constrained('recipes')->nullOnDelete();
            $table->text('description')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('presets');
    }
};

