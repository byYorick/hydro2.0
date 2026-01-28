<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Удаление legacy таблиц, которые больше не используются:
     * - zone_recipe_instances (заменено на grow_cycles + recipe_revisions)
     * - recipe_phases (legacy JSON targets, заменено на recipe_revision_phases)
     * - zone_cycles (дублирование, заменено на grow_cycles)
     * - plant_cycles (если существует, дублирование)
     * - commands_archive, zone_events_archive (дубли, retention через политики)
     * - recipe_stage_maps (заменено на stage_template_id в recipe_revision_phases)
     * 
     * Также удаляем старые таблицы инфраструктуры:
     * - zone_infrastructure (заменено на infrastructure_instances)
     * - infrastructure_assets (заменено на infrastructure_instances)
     * - zone_channel_bindings (заменено на channel_bindings)
     */
    public function up(): void
    {
        // Удаляем legacy таблицы рецептов и циклов
        Schema::dropIfExists('recipe_stage_maps');
        Schema::dropIfExists('zone_recipe_instances');
        Schema::dropIfExists('recipe_phases');
        Schema::dropIfExists('zone_cycles');
        Schema::dropIfExists('plant_cycles'); // Если существует
        
        // Удаляем архивные таблицы (retention через политики)
        Schema::dropIfExists('commands_archive');
        Schema::dropIfExists('zone_events_archive');
        
        // Удаляем старые таблицы инфраструктуры
        Schema::dropIfExists('zone_channel_bindings');
        Schema::dropIfExists('zone_infrastructure');
        Schema::dropIfExists('infrastructure_assets');
    }

    /**
     * Reverse the migrations.
     * 
     * ВНИМАНИЕ: Rollback не восстанавливает данные!
     * Это breaking change миграция.
     */
    public function down(): void
    {
        // Восстановление таблиц для rollback (без данных)
        // Это только для возможности отката структуры, данные не восстанавливаются
        
        // recipe_phases (legacy)
        Schema::create('recipe_phases', function (Blueprint $table) {
            $table->id();
            $table->foreignId('recipe_id')->constrained('recipes')->cascadeOnDelete();
            $table->integer('phase_index');
            $table->string('name');
            $table->integer('duration_hours')->nullable();
            $table->jsonb('targets')->nullable();
            $table->timestamps();
        });
        
        // zone_recipe_instances (legacy)
        Schema::create('zone_recipe_instances', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->foreignId('recipe_id')->constrained('recipes')->cascadeOnDelete();
            $table->integer('current_phase_index')->default(0);
            $table->timestamp('started_at')->nullable();
            $table->timestamps();
        });
        
        // zone_cycles (legacy)
        Schema::create('zone_cycles', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained()->cascadeOnDelete();
            $table->string('type', 64)->default('GROWTH_CYCLE');
            $table->string('status', 32)->default('active');
            $table->json('subsystems')->nullable();
            $table->timestampTz('started_at')->nullable();
            $table->timestampTz('ends_at')->nullable();
            $table->timestampsTz();
            $table->index(['zone_id', 'status']);
        });
        
        // recipe_stage_maps (legacy)
        Schema::create('recipe_stage_maps', function (Blueprint $table) {
            $table->id();
            $table->foreignId('recipe_id')->constrained('recipes')->cascadeOnDelete();
            $table->foreignId('stage_template_id')->constrained('grow_stage_templates')->cascadeOnDelete();
            $table->integer('order_index')->default(0);
            $table->integer('start_offset_days')->nullable();
            $table->integer('end_offset_days')->nullable();
            $table->jsonb('phase_indices')->nullable();
            $table->jsonb('targets_override')->nullable();
            $table->timestamps();
            $table->index(['recipe_id', 'order_index'], 'recipe_stage_maps_recipe_order_idx');
            $table->index('stage_template_id', 'recipe_stage_maps_stage_template_idx');
        });
        
        // zone_infrastructure (legacy)
        Schema::create('zone_infrastructure', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('asset_type');
            $table->string('label');
            $table->boolean('required')->default(false);
            $table->decimal('capacity_liters', 10, 2)->nullable();
            $table->decimal('flow_rate', 10, 2)->nullable();
            $table->jsonb('specs')->nullable();
            $table->timestamps();
            $table->index(['zone_id', 'asset_type']);
            $table->index(['zone_id', 'required']);
        });
        
        // infrastructure_assets (legacy)
        Schema::create('infrastructure_assets', function (Blueprint $table) {
            $table->id();
            $table->string('type');
            $table->string('name');
            $table->jsonb('metadata')->nullable();
            $table->timestamps();
            $table->index('type');
        });
        
        // zone_channel_bindings (legacy)
        Schema::create('zone_channel_bindings', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->foreignId('asset_id')->constrained('zone_infrastructure')->cascadeOnDelete();
            $table->foreignId('node_id')->constrained('nodes')->cascadeOnDelete();
            $table->string('channel');
            $table->string('direction');
            $table->string('role');
            $table->timestamps();
            $table->unique(['asset_id', 'node_id', 'channel'], 'zone_channel_bindings_unique');
            $table->index(['zone_id', 'asset_id']);
            $table->index(['node_id', 'channel']);
        });
        
        // Архивные таблицы (legacy)
        Schema::create('commands_archive', function (Blueprint $table) {
            $table->id();
            // Структура зависит от commands таблицы
            $table->timestamps();
        });
        
        Schema::create('zone_events_archive', function (Blueprint $table) {
            $table->id();
            // Структура зависит от zone_events таблицы
            $table->timestamps();
        });
    }
};

