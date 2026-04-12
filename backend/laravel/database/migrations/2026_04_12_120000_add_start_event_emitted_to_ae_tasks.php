<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table): void {
            if (! Schema::hasColumn('ae_tasks', 'start_event_emitted')) {
                $table->boolean('start_event_emitted')
                    ->notNull()
                    ->default(false)
                    ->after('updated_at');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table): void {
            if (Schema::hasColumn('ae_tasks', 'start_event_emitted')) {
                $table->dropColumn('start_event_emitted');
            }
        });
    }
};
