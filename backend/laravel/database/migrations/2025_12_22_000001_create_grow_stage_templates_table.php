<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('grow_stage_templates', function (Blueprint $table) {
            $table->id();
            $table->string('name', 128); // "Посадка", "Укоренение", "Вега", "Цветение", "Плодоношение", "Сбор"
            $table->string('code', 64)->unique(); // PLANTING/ROOTING/VEG/FLOWER/FRUIT/HARVEST
            $table->integer('order_index')->default(0); // Порядок отображения
            $table->integer('default_duration_days')->nullable(); // Длительность по умолчанию в днях
            $table->jsonb('ui_meta')->nullable(); // { color: string, icon: string, description: string }
            $table->timestamps();

            $table->index('code', 'grow_stage_templates_code_idx');
            $table->index('order_index', 'grow_stage_templates_order_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('grow_stage_templates');
    }
};

