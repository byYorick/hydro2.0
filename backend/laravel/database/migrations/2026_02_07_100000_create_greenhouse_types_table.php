<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('greenhouse_types', function (Blueprint $table) {
            $table->id();
            $table->string('code', 64)->unique();
            $table->string('name', 255);
            $table->text('description')->nullable();
            $table->boolean('is_active')->default(true);
            $table->unsignedSmallInteger('sort_order')->default(0);
            $table->timestamps();
        });

        DB::table('greenhouse_types')->insert([
            [
                'code' => 'indoor',
                'name' => 'Indoor',
                'description' => 'Закрытая теплица/помещение',
                'is_active' => true,
                'sort_order' => 10,
                'created_at' => now(),
                'updated_at' => now(),
            ],
            [
                'code' => 'greenhouse',
                'name' => 'Greenhouse',
                'description' => 'Классическая теплица',
                'is_active' => true,
                'sort_order' => 20,
                'created_at' => now(),
                'updated_at' => now(),
            ],
            [
                'code' => 'outdoor',
                'name' => 'Outdoor',
                'description' => 'Открытое выращивание',
                'is_active' => true,
                'sort_order' => 30,
                'created_at' => now(),
                'updated_at' => now(),
            ],
        ]);

        Schema::table('greenhouses', function (Blueprint $table) {
            $table->foreignId('greenhouse_type_id')
                ->nullable()
                ->constrained('greenhouse_types')
                ->nullOnDelete();
        });

        DB::statement("
            UPDATE greenhouses g
            SET greenhouse_type_id = gt.id
            FROM greenhouse_types gt
            WHERE g.type IS NOT NULL
              AND lower(g.type) = gt.code
        ");
    }

    public function down(): void
    {
        Schema::table('greenhouses', function (Blueprint $table) {
            $table->dropConstrainedForeignId('greenhouse_type_id');
        });

        Schema::dropIfExists('greenhouse_types');
    }
};

