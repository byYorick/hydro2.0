<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Снапшоты шагов фазы для конкретного цикла выращивания.
     * После старта цикла можно удалить/изменить шаблонные шаги — снапшот остаётся валиден.
     */
    public function up(): void
    {
        Schema::create('grow_cycle_phase_steps', function (Blueprint $table) {
            $table->id();
            $table->foreignId('grow_cycle_phase_id')->constrained('grow_cycle_phases')->cascadeOnDelete();
            $table->foreignId('recipe_revision_phase_step_id')->nullable()->constrained('recipe_revision_phase_steps')->nullOnDelete(); // Для трассировки
            $table->integer('step_index')->default(0); // Порядок шага в фазе
            $table->string('name'); // Название шага
            $table->integer('offset_hours')->default(0); // Смещение от начала фазы в часах
            $table->string('action')->nullable(); // Действие/задача шага
            $table->text('description')->nullable();
            
            // Уставки по колонкам (те же что у recipe_revision_phase_steps, nullable)
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
            
            $table->jsonb('extensions')->nullable(); // Только для расширений
            
            // Временные метки выполнения шага в цикле
            $table->timestamp('started_at')->nullable(); // Когда начался этот шаг в цикле
            $table->timestamp('ended_at')->nullable(); // Когда закончился этот шаг в цикле
            
            $table->timestamps();

            // Уникальность: одна фаза цикла не может иметь два шага с одинаковым индексом
            $table->unique(['grow_cycle_phase_id', 'step_index'], 'grow_cycle_phase_steps_phase_step_unique');
            $table->index('grow_cycle_phase_id', 'grow_cycle_phase_steps_phase_idx');
            $table->index('recipe_revision_phase_step_id', 'grow_cycle_phase_steps_revision_step_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('grow_cycle_phase_steps');
    }
};

