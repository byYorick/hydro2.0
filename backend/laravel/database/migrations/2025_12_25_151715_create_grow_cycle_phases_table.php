<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Снапшоты фаз ревизии рецепта для конкретного цикла выращивания.
     * После старта цикла можно удалить/изменить шаблонные фазы — снапшот остаётся валиден.
     */
    public function up(): void
    {
        Schema::create('grow_cycle_phases', function (Blueprint $table) {
            $table->id();
            $table->foreignId('grow_cycle_id')->constrained('grow_cycles')->cascadeOnDelete();
            $table->foreignId('recipe_revision_phase_id')->nullable()->constrained('recipe_revision_phases')->nullOnDelete(); // Для трассировки
            $table->integer('phase_index')->default(0); // Порядок фазы в цикле
            $table->string('name'); // Название фазы
            
            // Уставки по колонкам (те же что у recipe_revision_phases)
            $table->decimal('ph_target', 4, 2)->nullable();
            $table->decimal('ph_min', 4, 2)->nullable();
            $table->decimal('ph_max', 4, 2)->nullable();
            $table->decimal('ec_target', 5, 2)->nullable();
            $table->decimal('ec_min', 5, 2)->nullable();
            $table->decimal('ec_max', 5, 2)->nullable();
            $table->enum('irrigation_mode', ['SUBSTRATE', 'RECIRC'])->nullable();
            $table->integer('irrigation_interval_sec')->nullable();
            $table->integer('irrigation_duration_sec')->nullable();
            $table->integer('lighting_photoperiod_hours')->nullable();
            $table->time('lighting_start_time')->nullable();
            $table->integer('mist_interval_sec')->nullable();
            $table->integer('mist_duration_sec')->nullable();
            $table->enum('mist_mode', ['NORMAL', 'SPRAY'])->nullable();
            $table->decimal('temp_air_target', 5, 2)->nullable();
            $table->decimal('humidity_target', 5, 2)->nullable();
            $table->integer('co2_target')->nullable();
            
            // Прогресс
            $table->string('progress_model')->nullable(); // TIME|TIME_WITH_TEMP_CORRECTION|GDD
            $table->integer('duration_hours')->nullable();
            $table->integer('duration_days')->nullable();
            $table->decimal('base_temp_c', 4, 2)->nullable();
            $table->decimal('target_gdd', 8, 2)->nullable();
            $table->decimal('dli_target', 6, 2)->nullable();
            
            $table->jsonb('extensions')->nullable(); // Только для расширений
            
            // Временные метки выполнения фазы в цикле
            $table->timestamp('started_at')->nullable(); // Когда началась эта фаза в цикле
            $table->timestamp('ended_at')->nullable(); // Когда закончилась эта фаза в цикле
            
            $table->timestamps();

            // Уникальность: один цикл не может иметь две фазы с одинаковым индексом
            $table->unique(['grow_cycle_id', 'phase_index'], 'grow_cycle_phases_cycle_phase_unique');
            $table->index('grow_cycle_id', 'grow_cycle_phases_cycle_idx');
            $table->index('recipe_revision_phase_id', 'grow_cycle_phases_revision_phase_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('grow_cycle_phases');
    }
};

