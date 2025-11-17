<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('harvests', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->foreignId('recipe_id')->nullable()->constrained('recipes')->nullOnDelete();
            $table->date('harvest_date');
            $table->decimal('yield_weight_kg', 8, 2)->nullable(); // вес урожая в кг
            $table->integer('yield_count')->nullable(); // количество единиц (например, кочанов салата)
            $table->decimal('quality_score', 3, 2)->nullable(); // оценка качества 0.00-10.00
            $table->jsonb('notes')->nullable(); // дополнительные заметки
            $table->timestamps();
            $table->index(['zone_id', 'harvest_date']);
            $table->index('recipe_id');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('harvests');
    }
};

