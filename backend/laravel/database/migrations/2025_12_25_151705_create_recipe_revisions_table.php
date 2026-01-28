<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Ревизии рецептов - версионирование рецептов
     * Каждый рецепт может иметь несколько ревизий (DRAFT, PUBLISHED, ARCHIVED)
     */
    public function up(): void
    {
        Schema::create('recipe_revisions', function (Blueprint $table) {
            $table->id();
            $table->foreignId('recipe_id')->constrained('recipes')->cascadeOnDelete();
            $table->integer('revision_number')->default(1); // Номер ревизии (1, 2, 3...)
            $table->string('status')->default('DRAFT'); // DRAFT|PUBLISHED|ARCHIVED
            $table->text('description')->nullable(); // Описание изменений в этой ревизии
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('published_at')->nullable(); // Когда была опубликована
            $table->timestamps();

            // Уникальность: один рецепт не может иметь две ревизии с одинаковым номером
            $table->unique(['recipe_id', 'revision_number'], 'recipe_revisions_recipe_revision_unique');
            // Индекс для поиска опубликованных ревизий
            $table->index(['recipe_id', 'status'], 'recipe_revisions_recipe_status_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('recipe_revisions');
    }
};

