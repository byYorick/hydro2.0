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
        Schema::create('zone_simulations', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->jsonb('scenario'); // {recipe_id, initial_state: {ph, ec, temp_air, temp_water}}
            $table->jsonb('results')->nullable(); // временные ряды параметров
            $table->integer('duration_hours');
            $table->integer('step_minutes')->default(10);
            $table->string('status')->default('pending'); // pending, running, completed, failed
            $table->text('error_message')->nullable();
            $table->timestamps();
            
            $table->index(['zone_id', 'created_at']);
            $table->index('status');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('zone_simulations');
    }
};
