<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('recipe_analytics', function (Blueprint $table) {
            $table->id();
            $table->foreignId('recipe_id')->constrained('recipes')->cascadeOnDelete();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->timestamp('start_date');
            $table->timestamp('end_date')->nullable();
            $table->integer('total_duration_hours')->nullable(); // фактическая длительность в часах
            $table->decimal('avg_ph_deviation', 6, 3)->nullable(); // среднее отклонение pH от целевого
            $table->decimal('avg_ec_deviation', 6, 3)->nullable(); // среднее отклонение EC от целевого
            $table->integer('alerts_count')->default(0); // количество аварий/предупреждений
            $table->jsonb('final_yield')->nullable(); // итоговый урожай {weight_kg, count, quality_score}
            $table->decimal('efficiency_score', 5, 2)->nullable(); // оценка эффективности 0.00-100.00
            $table->jsonb('additional_metrics')->nullable(); // дополнительные метрики
            $table->timestamps();
            $table->index(['recipe_id', 'zone_id']);
            $table->index(['start_date', 'end_date']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('recipe_analytics');
    }
};

