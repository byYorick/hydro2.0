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
            if (! Schema::hasColumn('ae_tasks', 'corr_snapshot_event_id')) {
                $table->unsignedBigInteger('corr_snapshot_event_id')
                    ->nullable()
                    ->after('corr_ph_amount_ml');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_snapshot_created_at')) {
                $table->timestamp('corr_snapshot_created_at')
                    ->nullable()
                    ->after('corr_snapshot_event_id');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_snapshot_cmd_id')) {
                $table->string('corr_snapshot_cmd_id')
                    ->nullable()
                    ->after('corr_snapshot_created_at');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_snapshot_source_event_type')) {
                $table->string('corr_snapshot_source_event_type')
                    ->nullable()
                    ->after('corr_snapshot_cmd_id');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table): void {
            $drops = array_values(array_filter([
                Schema::hasColumn('ae_tasks', 'corr_snapshot_source_event_type') ? 'corr_snapshot_source_event_type' : null,
                Schema::hasColumn('ae_tasks', 'corr_snapshot_cmd_id') ? 'corr_snapshot_cmd_id' : null,
                Schema::hasColumn('ae_tasks', 'corr_snapshot_created_at') ? 'corr_snapshot_created_at' : null,
                Schema::hasColumn('ae_tasks', 'corr_snapshot_event_id') ? 'corr_snapshot_event_id' : null,
            ]));

            if ($drops !== []) {
                $table->dropColumn($drops);
            }
        });
    }
};
