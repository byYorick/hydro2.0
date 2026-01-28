<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Перекрытия целевых параметров для активного цикла
     * Таблица лучше чем JSONB для аудита и истории изменений
     */
    public function up(): void
    {
        Schema::create('grow_cycle_overrides', function (Blueprint $table) {
            $table->id();
            $table->foreignId('grow_cycle_id')->constrained('grow_cycles')->cascadeOnDelete();
            $table->string('parameter'); // ph_target, ec_target, irrigation_interval_sec, etc
            $table->string('value_type')->default('decimal'); // decimal|integer|string|boolean|time
            $table->text('value'); // Значение как строка (для гибкости)
            $table->text('reason')->nullable(); // Причина перекрытия
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('applies_from')->nullable(); // С какого момента применяется
            $table->timestamp('applies_until')->nullable(); // До какого момента применяется
            $table->boolean('is_active')->default(true);
            $table->timestamps();

            // Индексы для быстрого поиска активных перекрытий
            $table->index(['grow_cycle_id', 'is_active'], 'grow_cycle_overrides_cycle_active_idx');
            $table->index(['grow_cycle_id', 'parameter'], 'grow_cycle_overrides_cycle_parameter_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('grow_cycle_overrides');
    }
};

