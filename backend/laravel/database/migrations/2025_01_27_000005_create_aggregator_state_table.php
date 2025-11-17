<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('aggregator_state', function (Blueprint $table) {
            $table->id();
            $table->string('aggregation_type', 32)->unique(); // '1m', '1h', 'daily'
            $table->timestamp('last_ts')->nullable(); // Последняя обработанная временная метка
            $table->timestamp('updated_at')->useCurrent();
            
            $table->index('aggregation_type');
        });
        
        // Инициализируем состояние агрегации
        DB::table('aggregator_state')->insert([
            ['aggregation_type' => '1m', 'last_ts' => null, 'updated_at' => now()],
            ['aggregation_type' => '1h', 'last_ts' => null, 'updated_at' => now()],
            ['aggregation_type' => 'daily', 'last_ts' => null, 'updated_at' => now()],
        ]);
    }

    public function down(): void
    {
        Schema::dropIfExists('aggregator_state');
    }
};

