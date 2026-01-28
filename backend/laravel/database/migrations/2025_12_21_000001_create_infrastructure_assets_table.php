<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Глобальный каталог типов оборудования
     */
    public function up(): void
    {
        Schema::create('infrastructure_assets', function (Blueprint $table) {
            $table->id();
            $table->string('type'); // PUMP|MISTER|TANK_NUTRIENT|TANK_CLEAN|DRAIN|LIGHT|VENT|HEATER
            $table->string('name');
            $table->jsonb('metadata')->nullable(); // Дополнительные метаданные
            $table->timestamps();
            
            $table->index('type');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('infrastructure_assets');
    }
};

