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

        Schema::table('ae_tasks', function (Blueprint $table) {
            if (! Schema::hasColumn('ae_tasks', 'irrigation_decision_config')) {
                $table->jsonb('irrigation_decision_config')->nullable()->after('irrigation_decision_strategy');
            }

            if (! Schema::hasColumn('ae_tasks', 'irrigation_bundle_revision')) {
                $table->string('irrigation_bundle_revision', 64)->nullable()->after('irrigation_decision_config');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            foreach (['irrigation_bundle_revision', 'irrigation_decision_config'] as $column) {
                if (Schema::hasColumn('ae_tasks', $column)) {
                    $table->dropColumn($column);
                }
            }
        });
    }
};
