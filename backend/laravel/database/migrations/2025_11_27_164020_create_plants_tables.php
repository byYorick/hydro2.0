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
        Schema::create('plants', function (Blueprint $table) {
            $table->id();
            $table->string('slug')->unique();
            $table->string('name');
            $table->string('species')->nullable();
            $table->string('variety')->nullable();
            $table->string('substrate_type')->nullable()->index();
            $table->string('growing_system')->nullable()->index();
            $table->string('photoperiod_preset')->nullable();
            $table->string('seasonality')->nullable();
            $table->string('icon_path')->nullable();
            $table->text('description')->nullable();
            $table->json('environment_requirements')->nullable();
            $table->json('growth_phases')->nullable();
            $table->json('recommended_recipes')->nullable();
            $table->json('metadata')->nullable();
            $table->timestamps();
        });

        Schema::create('plant_zone', function (Blueprint $table) {
            $table->id();
            $table->foreignId('plant_id')->constrained()->cascadeOnDelete();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->timestamp('assigned_at')->nullable();
            $table->json('metadata')->nullable();
            $table->timestamps();

            $table->unique(['plant_id', 'zone_id']);
        });

        Schema::create('plant_recipe', function (Blueprint $table) {
            $table->id();
            $table->foreignId('plant_id')->constrained()->cascadeOnDelete();
            $table->foreignId('recipe_id')->constrained()->cascadeOnDelete();
            $table->string('season')->nullable();
            $table->string('site_type')->nullable();
            $table->boolean('is_default')->default(false);
            $table->json('metadata')->nullable();
            $table->timestamps();

            $table->unique(['plant_id', 'recipe_id', 'season', 'site_type']);
        });

        Schema::create('plant_cycles', function (Blueprint $table) {
            $table->id();
            $table->foreignId('plant_id')->constrained()->cascadeOnDelete();
            $table->unsignedBigInteger('cycle_id')->nullable()->index();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->string('season')->nullable();
            $table->json('settings')->nullable();
            $table->json('metrics_snapshot')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('plant_cycles');
        Schema::dropIfExists('plant_recipe');
        Schema::dropIfExists('plant_zone');
        Schema::dropIfExists('plants');
    }
};
