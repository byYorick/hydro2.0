<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Оборудование, установленное в зоне
     */
    public function up(): void
    {
        Schema::create('zone_infrastructure', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('asset_type'); // PUMP|MISTER|TANK_NUTRIENT|TANK_CLEAN|DRAIN|LIGHT|VENT|HEATER
            $table->string('label'); // Название/метка оборудования в зоне
            $table->boolean('required')->default(false); // Обязательное ли оборудование
            $table->decimal('capacity_liters', 10, 2)->nullable(); // Для баков
            $table->decimal('flow_rate', 10, 2)->nullable(); // Для насосов/мистеров
            $table->jsonb('specs')->nullable(); // Дополнительные характеристики
            $table->timestamps();
            
            $table->index(['zone_id', 'asset_type']);
            $table->index(['zone_id', 'required']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('zone_infrastructure');
    }
};

