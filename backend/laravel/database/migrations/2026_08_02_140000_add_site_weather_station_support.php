<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Str;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('greenhouses', function (Blueprint $table) {
            $table->boolean('is_system')->default(false)->after('description');
        });

        Schema::table('greenhouses', function (Blueprint $table) {
            $table->foreignId('shared_weather_station_node_id')
                ->nullable()
                ->after('is_system')
                ->constrained('nodes')
                ->nullOnDelete();
        });

        $now = now();
        $siteId = DB::table('greenhouses')->where('uid', 'site')->value('id');

        if ($siteId === null) {
            $siteId = DB::table('greenhouses')->insertGetId([
                'uid' => 'site',
                'name' => 'Site Infrastructure',
                'timezone' => 'UTC',
                'type' => 'system',
                'description' => 'Hidden system greenhouse for site-level devices (weather stations).',
                'provisioning_token' => 'gh_'.Str::random(32),
                'is_system' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        } else {
            DB::table('greenhouses')->where('id', $siteId)->update([
                'is_system' => true,
                'updated_at' => $now,
            ]);
        }

        $wxExists = DB::table('zones')->where('uid', 'wx')->exists();
        if (! $wxExists) {
            DB::table('zones')->insert([
                'uid' => 'wx',
                'name' => 'Site Weather',
                'description' => 'MQTT transport anchor for site-level weather stations.',
                'status' => 'online',
                'greenhouse_id' => $siteId,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }
    }

    public function down(): void
    {
        Schema::table('greenhouses', function (Blueprint $table) {
            $table->dropConstrainedForeignId('shared_weather_station_node_id');
        });

        Schema::table('greenhouses', function (Blueprint $table) {
            $table->dropColumn('is_system');
        });
    }
};
