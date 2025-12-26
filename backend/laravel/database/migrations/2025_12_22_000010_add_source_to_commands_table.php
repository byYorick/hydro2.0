<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('commands', function (Blueprint $table) {
            if (! Schema::hasColumn('commands', 'source')) {
                $table->string('source')->nullable()->after('status');
                $table->index('source', 'commands_source_idx');
            }
        });
    }

    public function down(): void
    {
        Schema::table('commands', function (Blueprint $table) {
            if (Schema::hasColumn('commands', 'source')) {
                $table->dropIndex('commands_source_idx');
                $table->dropColumn('source');
            }
        });
    }
};








