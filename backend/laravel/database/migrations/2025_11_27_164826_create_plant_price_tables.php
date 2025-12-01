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
        Schema::create('plant_price_versions', function (Blueprint $table) {
            $table->id();
            $table->foreignId('plant_id')->constrained()->cascadeOnDelete();
            $table->date('effective_from')->nullable();
            $table->date('effective_to')->nullable();
            $table->string('currency', 8)->default('RUB');
            $table->decimal('seedling_cost', 12, 2)->nullable();
            $table->decimal('substrate_cost', 12, 2)->nullable();
            $table->decimal('nutrient_cost', 12, 2)->nullable();
            $table->decimal('labor_cost', 12, 2)->nullable();
            $table->decimal('protection_cost', 12, 2)->nullable();
            $table->decimal('logistics_cost', 12, 2)->nullable();
            $table->decimal('other_cost', 12, 2)->nullable();
            $table->decimal('wholesale_price', 12, 2)->nullable();
            $table->decimal('retail_price', 12, 2)->nullable();
            $table->string('source')->nullable();
            $table->json('metadata')->nullable();
            $table->timestamps();

            $table->index(['plant_id', 'effective_from', 'effective_to']);
        });

        Schema::create('plant_cost_items', function (Blueprint $table) {
            $table->id();
            $table->foreignId('plant_id')->constrained()->cascadeOnDelete();
            $table->foreignId('plant_price_version_id')->nullable()->constrained()->cascadeOnDelete();
            $table->string('type');
            $table->decimal('amount', 12, 2);
            $table->string('currency', 8)->default('RUB');
            $table->string('notes')->nullable();
            $table->json('metadata')->nullable();
            $table->timestamps();
        });

        Schema::create('plant_sale_prices', function (Blueprint $table) {
            $table->id();
            $table->foreignId('plant_id')->constrained()->cascadeOnDelete();
            $table->foreignId('plant_price_version_id')->nullable()->constrained()->cascadeOnDelete();
            $table->string('channel');
            $table->decimal('price', 12, 2);
            $table->string('currency', 8)->default('RUB');
            $table->boolean('is_active')->default(true);
            $table->json('metadata')->nullable();
            $table->timestamps();

            $table->index(['plant_id', 'channel']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('plant_sale_prices');
        Schema::dropIfExists('plant_cost_items');
        Schema::dropIfExists('plant_price_versions');
    }
};
