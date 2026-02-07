<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('nutrient_products', function (Blueprint $table) {
            $table->id();
            $table->string('manufacturer', 128);
            $table->string('name', 191);
            $table->string('component', 16); // npk | calcium | micro
            $table->string('composition', 128)->nullable();
            $table->string('recommended_stage', 64)->nullable();
            $table->text('notes')->nullable();
            $table->jsonb('metadata')->nullable();
            $table->timestamps();

            $table->index(['component'], 'nutrient_products_component_idx');
            $table->unique(['manufacturer', 'name', 'component'], 'nutrient_products_unique_name_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('nutrient_products');
    }
};
