<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            if (!Schema::hasColumn('nodes', 'last_heartbeat_at')) {
                $table->timestamp('last_heartbeat_at')->nullable()->after('last_seen_at');
            }
            if (!Schema::hasColumn('nodes', 'uptime_seconds')) {
                $table->integer('uptime_seconds')->nullable()->after('last_heartbeat_at');
                // Время работы узла в секундах (uptime)
            }
            if (!Schema::hasColumn('nodes', 'free_heap_bytes')) {
                $table->integer('free_heap_bytes')->nullable()->after('uptime_seconds');
                // Свободная память в байтах (free heap)
            }
            if (!Schema::hasColumn('nodes', 'rssi')) {
                $table->integer('rssi')->nullable()->after('free_heap_bytes');
                // Сила сигнала Wi-Fi (RSSI в dBm)
            }
        });
    }

    public function down(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            if (Schema::hasColumn('nodes', 'last_heartbeat_at')) {
                $table->dropColumn('last_heartbeat_at');
            }
            if (Schema::hasColumn('nodes', 'uptime_seconds')) {
                $table->dropColumn('uptime_seconds');
            }
            if (Schema::hasColumn('nodes', 'free_heap_bytes')) {
                $table->dropColumn('free_heap_bytes');
            }
            if (Schema::hasColumn('nodes', 'rssi')) {
                $table->dropColumn('rssi');
            }
        });
    }
};
