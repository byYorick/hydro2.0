<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Полиморфная инфраструктура - заменяет zone_infrastructure + infrastructure_assets
     * owner_type: 'zone' | 'greenhouse'
     * owner_id: ID зоны или теплицы
     */
    public function up(): void
    {
        Schema::create('infrastructure_instances', function (Blueprint $table) {
            $table->id();
            $table->string('owner_type'); // zone|greenhouse
            $table->unsignedBigInteger('owner_id');
            $table->enum('asset_type', [
                'PUMP',
                'MISTER',
                'TANK_CLEAN',
                'TANK_WORKING',
                'TANK_NUTRIENT',
                'DRAIN',
                'LIGHT',
                'VENT',
                'HEATER',
                'FAN',
                'CO2_INJECTOR',
                'OTHER'
            ]);
            $table->string('label'); // Название/метка оборудования
            $table->boolean('required')->default(false); // Обязательное ли оборудование
            $table->decimal('capacity_liters', 10, 2)->nullable(); // Для баков
            $table->decimal('flow_rate', 10, 2)->nullable(); // Для насосов/мистеров
            $table->jsonb('specs')->nullable(); // Дополнительные характеристики
            $table->timestamps();

            // Индексы
            $table->index(['owner_type', 'owner_id'], 'infrastructure_instances_owner_idx');
            $table->index(['owner_type', 'owner_id', 'asset_type'], 'infrastructure_instances_owner_type_idx');
            $table->index(['owner_type', 'owner_id', 'required'], 'infrastructure_instances_owner_required_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('infrastructure_instances');
    }
};

